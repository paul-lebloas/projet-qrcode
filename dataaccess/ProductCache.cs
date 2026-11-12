using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using StackExchange.Redis;

namespace DataAccess;

public sealed record CacheSettings(TimeSpan Ttl, TimeSpan NegativeTtl, TimeSpan SearchTtl);

/// <summary>Résultat d'une lecture : la valeur et l'origine (HIT, MISS ou BYPASS si Redis est indisponible).</summary>
public sealed record CacheResult<T>(T Value, string Status);

/// <summary>
/// Cache Redis en « cache-aside » :
///   lecture  -> Redis ; en cas d'absence, PostgreSQL puis écriture dans Redis avec TTL ;
///   écriture -> PostgreSQL puis invalidation des clés concernées.
/// Un produit inconnu est mémorisé brièvement (cache négatif) pour éviter de
/// solliciter PostgreSQL à chaque scan d'un code absent de la base.
/// Si Redis tombe, le service continue de répondre directement depuis PostgreSQL.
/// </summary>
public sealed class ProductCache(IConnectionMultiplexer redis, CacheSettings settings, ILogger<ProductCache> logger)
{
    private const string NotFoundMarker = "null";
    private const string SearchVersionKey = "search:version";

    private long _hits;
    private long _misses;

    public static string EanKey(string ean) => $"product:ean:{ean}";

    // Le contenu d'un QR Code peut être long : on le condense pour garder des clés courtes.
    public static string QrKey(string qr) => $"product:qr:{Sha256(qr)}";

    public async Task<CacheResult<Product?>> GetOrLoadProductAsync(string key, Func<Task<Product?>> loader)
    {
        var cached = await TryGetAsync(key);
        if (cached is not null)
        {
            var product = cached == NotFoundMarker ? null : Deserialize<Product>(cached);
            if (cached == NotFoundMarker || product is not null)
            {
                Interlocked.Increment(ref _hits);
                return new CacheResult<Product?>(product, "HIT");
            }
        }

        var loaded = await loader();
        var stored = loaded is null
            ? await TrySetAsync(key, NotFoundMarker, settings.NegativeTtl)
            : await TrySetAsync(key, JsonSerializer.Serialize(loaded, JsonDefaults.Options), settings.Ttl);

        Interlocked.Increment(ref _misses);
        return new CacheResult<Product?>(loaded, stored ? "MISS" : "BYPASS");
    }

    public async Task<CacheResult<IReadOnlyList<Product>>> GetOrLoadSearchAsync(
        string normalizedQuery, int limit, Func<Task<IReadOnlyList<Product>>> loader)
    {
        var version = await TryGetAsync(SearchVersionKey) ?? "0";
        var key = $"search:v{version}:{limit}:{Sha256(normalizedQuery)}";

        var cached = await TryGetAsync(key);
        if (cached is not null)
        {
            var items = Deserialize<List<Product>>(cached);
            if (items is not null)
            {
                Interlocked.Increment(ref _hits);
                return new CacheResult<IReadOnlyList<Product>>(items, "HIT");
            }
        }

        var loaded = await loader();
        var stored = await TrySetAsync(key, JsonSerializer.Serialize(loaded, JsonDefaults.Options), settings.SearchTtl);

        Interlocked.Increment(ref _misses);
        return new CacheResult<IReadOnlyList<Product>>(loaded, stored ? "MISS" : "BYPASS");
    }

    /// <summary>Après une écriture : supprime les entrées produit et invalide toutes les recherches en cache.</summary>
    public async Task InvalidateAsync(params Product?[] products)
    {
        try
        {
            var db = redis.GetDatabase();
            var keys = new List<RedisKey>();
            foreach (var p in products)
            {
                if (p?.Ean13 is not null) keys.Add(EanKey(p.Ean13));
                if (p?.QrCode is not null) keys.Add(QrKey(p.QrCode));
            }

            if (keys.Count > 0)
            {
                await db.KeyDeleteAsync(keys.ToArray());
            }

            // Les clés de recherche embarquent ce numéro de version : l'incrémenter les rend toutes obsolètes.
            await db.StringIncrementAsync(SearchVersionKey);
        }
        catch (RedisException ex)
        {
            logger.LogWarning(ex, "Invalidation du cache impossible (Redis indisponible).");
        }
    }

    public async Task<bool> PingAsync()
    {
        try
        {
            await redis.GetDatabase().PingAsync();
            return true;
        }
        catch (RedisException)
        {
            return false;
        }
    }

    public async Task<CacheStats> GetStatsAsync()
    {
        var hits = Interlocked.Read(ref _hits);
        var misses = Interlocked.Read(ref _misses);
        var total = hits + misses;
        return new CacheStats(hits, misses, total == 0 ? 0 : Math.Round((double)hits / total, 4),
            await PingAsync() ? "up" : "down");
    }

    private async Task<string?> TryGetAsync(string key)
    {
        try
        {
            var value = await redis.GetDatabase().StringGetAsync(key);
            return value.HasValue ? (string?)value : null;
        }
        catch (RedisException ex)
        {
            logger.LogWarning(ex, "Lecture Redis impossible, repli sur PostgreSQL.");
            return null;
        }
    }

    private async Task<bool> TrySetAsync(string key, string value, TimeSpan ttl)
    {
        try
        {
            return await redis.GetDatabase().StringSetAsync(key, value, ttl);
        }
        catch (RedisException ex)
        {
            logger.LogWarning(ex, "Écriture Redis impossible.");
            return false;
        }
    }

    private static T? Deserialize<T>(string json)
    {
        try
        {
            return JsonSerializer.Deserialize<T>(json, JsonDefaults.Options);
        }
        catch (JsonException)
        {
            return default;
        }
    }

    private static string Sha256(string value) =>
        Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant();
}
