using System.Text.Json;

namespace DataAccess;

/// <summary>Produit tel que stocké dans PostgreSQL (sérialisé en snake_case).</summary>
public sealed record Product(
    long Id,
    string? Ean13,
    string? QrCode,
    string Name,
    string? Brand,
    string? Category,
    string? Description,
    DateTimeOffset CreatedAt,
    DateTimeOffset UpdatedAt);

/// <summary>Corps des requêtes POST / PUT. Tous les champs sont validés avant écriture.</summary>
public sealed record ProductInput(
    string? Ean13,
    string? QrCode,
    string? Name,
    string? Brand,
    string? Category,
    string? Description);

public sealed record SearchResult(IReadOnlyList<Product> Items);

public sealed record CacheStats(long Hits, long Misses, double HitRatio, string Redis);

/// <summary>Options JSON partagées : API HTTP et valeurs stockées dans Redis.</summary>
public static class JsonDefaults
{
    public static readonly JsonSerializerOptions Options = new(JsonSerializerDefaults.Web)
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
    };
}
