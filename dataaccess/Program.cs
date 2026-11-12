using System.Text.Json;
using DataAccess;
using Npgsql;
using StackExchange.Redis;

var builder = WebApplication.CreateBuilder(args);

static string Env(string name, string? fallback = null) =>
    Environment.GetEnvironmentVariable(name) ?? fallback
    ?? throw new InvalidOperationException($"Variable d'environnement manquante : {name}");

builder.Services.ConfigureHttpJsonOptions(o =>
{
    o.SerializerOptions.PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower;
    o.SerializerOptions.PropertyNameCaseInsensitive = true;
});

// --- PostgreSQL (seul service autorisé à s'y connecter) ---
var pg = new NpgsqlConnectionStringBuilder
{
    Host = Env("POSTGRES_HOST"),
    Database = Env("POSTGRES_DB"),
    Username = Env("POSTGRES_USER"),
    Password = Env("POSTGRES_PASSWORD"),
    MaxPoolSize = 20,
};
builder.Services.AddSingleton(NpgsqlDataSource.Create(pg.ConnectionString));
builder.Services.AddSingleton<ProductRepository>();

// --- Redis (cache) ---
var redisOptions = new ConfigurationOptions
{
    EndPoints = { $"{Env("REDIS_HOST")}:6379" },
    Password = Env("REDIS_PASSWORD"),
    AbortOnConnectFail = false, // démarre même si Redis n'est pas encore prêt, se reconnecte seul
    ConnectTimeout = 2000,
    SyncTimeout = 1000,
    AsyncTimeout = 1000,
};
builder.Services.AddSingleton<IConnectionMultiplexer>(_ => ConnectionMultiplexer.Connect(redisOptions));
builder.Services.AddSingleton(new CacheSettings(
    Ttl: TimeSpan.FromSeconds(int.Parse(Env("CACHE_TTL_SECONDS", "600"))),
    NegativeTtl: TimeSpan.FromSeconds(int.Parse(Env("CACHE_NEGATIVE_TTL_SECONDS", "60"))),
    SearchTtl: TimeSpan.FromSeconds(30)));
builder.Services.AddSingleton<ProductCache>();

var app = builder.Build();

app.UseExceptionHandler(handler => handler.Run(async ctx =>
{
    ctx.Response.StatusCode = StatusCodes.Status500InternalServerError;
    await ctx.Response.WriteAsJsonAsync(new { error = "Erreur interne du service Data Access." });
}));

// ---------------------------------------------------------------- Santé
app.MapGet("/health", () => Results.Ok(new { status = "ok" }));

app.MapGet("/ready", async (ProductRepository repo, ProductCache cache) =>
{
    try
    {
        await repo.PingAsync();
    }
    catch (NpgsqlException)
    {
        return Results.Json(new { status = "postgres_unavailable" }, statusCode: StatusCodes.Status503ServiceUnavailable);
    }

    return Results.Ok(new { status = "ok", redis = await cache.PingAsync() ? "up" : "down" });
});

app.MapGet("/cache/stats", async (ProductCache cache) => Results.Ok(await cache.GetStatsAsync()));

// ---------------------------------------------------------------- Lecture
// Recherche d'un produit par EAN-13 ou par contenu de QR Code (en-tête X-Cache : HIT / MISS / BYPASS).
app.MapGet("/products/lookup", async (string? ean13, string? qr, ProductRepository repo, ProductCache cache, HttpResponse res) =>
{
    if (string.IsNullOrWhiteSpace(ean13) == string.IsNullOrWhiteSpace(qr))
    {
        return Results.ValidationProblem(new Dictionary<string, string[]>
        {
            ["identifier"] = ["Fournir exactement un paramètre : ean13 ou qr."],
        });
    }

    CacheResult<Product?> result;
    if (!string.IsNullOrWhiteSpace(ean13))
    {
        var ean = ean13.Trim();
        if (!Ean13Validator.IsValid(ean))
        {
            return Results.ValidationProblem(new Dictionary<string, string[]>
            {
                ["ean13"] = ["EAN-13 invalide : 13 chiffres avec clé de contrôle correcte attendus."],
            });
        }

        result = await cache.GetOrLoadProductAsync(ProductCache.EanKey(ean), () => repo.GetByEanAsync(ean));
    }
    else
    {
        var code = qr!.Trim();
        if (code.Length is 0 or > 2048)
        {
            return Results.ValidationProblem(new Dictionary<string, string[]>
            {
                ["qr"] = ["Le contenu du QR Code doit faire entre 1 et 2048 caractères."],
            });
        }

        result = await cache.GetOrLoadProductAsync(ProductCache.QrKey(code), () => repo.GetByQrAsync(code));
    }

    res.Headers["X-Cache"] = result.Status;
    return result.Value is null
        ? Results.NotFound(new { error = "Produit inconnu." })
        : Results.Ok(result.Value);
});

app.MapGet("/products/search", async (string? q, int? limit, ProductRepository repo, ProductCache cache, HttpResponse res) =>
{
    var normalized = (q ?? string.Empty).Trim().ToLowerInvariant();
    if (normalized.Length > 100)
    {
        return Results.ValidationProblem(new Dictionary<string, string[]>
        {
            ["q"] = ["La recherche ne doit pas dépasser 100 caractères."],
        });
    }

    var max = Math.Clamp(limit ?? 20, 1, 50);
    var result = await cache.GetOrLoadSearchAsync(normalized, max, () => repo.SearchAsync(normalized, max));
    res.Headers["X-Cache"] = result.Status;
    return Results.Ok(new SearchResult(result.Value));
});

app.MapGet("/products/{id:long}", async (long id, ProductRepository repo) =>
    await repo.GetByIdAsync(id) is { } product
        ? Results.Ok(product)
        : Results.NotFound(new { error = "Produit inconnu." }));

// ---------------------------------------------------------------- Écriture
app.MapPost("/products", async (ProductInput? body, ProductRepository repo, ProductCache cache) =>
{
    var (input, errors) = ProductValidation.Validate(body);
    if (errors is not null)
    {
        return Results.ValidationProblem(errors);
    }

    try
    {
        var created = await repo.CreateAsync(input!);
        await cache.InvalidateAsync(created);
        return Results.Created($"/products/{created!.Id}", created);
    }
    catch (PostgresException ex) when (ex.SqlState == PostgresErrorCodes.UniqueViolation)
    {
        return Results.Conflict(new { error = "Un produit existe déjà avec cet EAN-13 ou ce QR Code." });
    }
});

app.MapPut("/products/{id:long}", async (long id, ProductInput? body, ProductRepository repo, ProductCache cache) =>
{
    var (input, errors) = ProductValidation.Validate(body);
    if (errors is not null)
    {
        return Results.ValidationProblem(errors);
    }

    var before = await repo.GetByIdAsync(id);
    if (before is null)
    {
        return Results.NotFound(new { error = "Produit inconnu." });
    }

    try
    {
        var updated = await repo.UpdateAsync(id, input!);
        await cache.InvalidateAsync(before, updated);
        return Results.Ok(updated);
    }
    catch (PostgresException ex) when (ex.SqlState == PostgresErrorCodes.UniqueViolation)
    {
        return Results.Conflict(new { error = "Un autre produit utilise déjà cet EAN-13 ou ce QR Code." });
    }
});

app.MapDelete("/products/{id:long}", async (long id, ProductRepository repo, ProductCache cache) =>
{
    var existing = await repo.GetByIdAsync(id);
    if (existing is null || !await repo.DeleteAsync(id))
    {
        return Results.NotFound(new { error = "Produit inconnu." });
    }

    await cache.InvalidateAsync(existing);
    return Results.NoContent();
});

app.Run();
