using Npgsql;
using NpgsqlTypes;

namespace DataAccess;

/// <summary>
/// Seul point d'accès à PostgreSQL de toute l'application.
/// Requêtes toujours paramétrées (aucune concaténation de valeurs utilisateur).
/// </summary>
public sealed class ProductRepository(NpgsqlDataSource dataSource)
{
    private const string Columns =
        "id, ean13, qr_code, name, brand, category, description, created_at, updated_at";

    public Task<Product?> GetByIdAsync(long id) =>
        QuerySingleAsync($"SELECT {Columns} FROM products WHERE id = @id",
            new NpgsqlParameter("id", NpgsqlDbType.Bigint) { Value = id });

    public Task<Product?> GetByEanAsync(string ean) =>
        QuerySingleAsync($"SELECT {Columns} FROM products WHERE ean13 = @ean", Text("ean", ean));

    public Task<Product?> GetByQrAsync(string qr) =>
        QuerySingleAsync($"SELECT {Columns} FROM products WHERE qr_code = @qr", Text("qr", qr));

    public async Task<IReadOnlyList<Product>> SearchAsync(string? q, int limit)
    {
        var pattern = "%" + EscapeLike(q ?? string.Empty) + "%";

        await using var cmd = dataSource.CreateCommand(
            $@"SELECT {Columns} FROM products
               WHERE name ILIKE @p ESCAPE '\' OR brand ILIKE @p ESCAPE '\' OR category ILIKE @p ESCAPE '\'
               ORDER BY name
               LIMIT @limit");
        cmd.Parameters.Add(Text("p", pattern));
        cmd.Parameters.Add(new NpgsqlParameter("limit", NpgsqlDbType.Integer) { Value = limit });

        var items = new List<Product>();
        await using var reader = await cmd.ExecuteReaderAsync();
        while (await reader.ReadAsync())
        {
            items.Add(Map(reader));
        }

        return items;
    }

    public Task<Product?> CreateAsync(ProductInput input) =>
        QuerySingleAsync(
            $@"INSERT INTO products (ean13, qr_code, name, brand, category, description)
               VALUES (@ean13, @qr, @name, @brand, @category, @description)
               RETURNING {Columns}",
            WriteParameters(input));

    public Task<Product?> UpdateAsync(long id, ProductInput input)
    {
        var parameters = WriteParameters(input)
            .Append(new NpgsqlParameter("id", NpgsqlDbType.Bigint) { Value = id })
            .ToArray();

        return QuerySingleAsync(
            $@"UPDATE products
               SET ean13 = @ean13, qr_code = @qr, name = @name, brand = @brand,
                   category = @category, description = @description, updated_at = now()
               WHERE id = @id
               RETURNING {Columns}",
            parameters);
    }

    public async Task<bool> DeleteAsync(long id)
    {
        await using var cmd = dataSource.CreateCommand("DELETE FROM products WHERE id = @id");
        cmd.Parameters.Add(new NpgsqlParameter("id", NpgsqlDbType.Bigint) { Value = id });
        return await cmd.ExecuteNonQueryAsync() > 0;
    }

    public async Task PingAsync()
    {
        await using var cmd = dataSource.CreateCommand("SELECT 1");
        await cmd.ExecuteScalarAsync();
    }

    private async Task<Product?> QuerySingleAsync(string sql, params NpgsqlParameter[] parameters)
    {
        await using var cmd = dataSource.CreateCommand(sql);
        cmd.Parameters.AddRange(parameters);
        await using var reader = await cmd.ExecuteReaderAsync();
        return await reader.ReadAsync() ? Map(reader) : null;
    }

    private static NpgsqlParameter[] WriteParameters(ProductInput input) =>
    [
        Text("ean13", input.Ean13),
        Text("qr", input.QrCode),
        Text("name", input.Name),
        Text("brand", input.Brand),
        Text("category", input.Category),
        Text("description", input.Description),
    ];

    private static NpgsqlParameter Text(string name, string? value) =>
        new(name, NpgsqlDbType.Text) { Value = (object?)value ?? DBNull.Value };

    private static string? NullableString(NpgsqlDataReader r, int i) =>
        r.IsDBNull(i) ? null : r.GetString(i);

    private static Product Map(NpgsqlDataReader r) => new(
        r.GetInt64(0),
        NullableString(r, 1),
        NullableString(r, 2),
        r.GetString(3),
        NullableString(r, 4),
        NullableString(r, 5),
        NullableString(r, 6),
        r.GetFieldValue<DateTimeOffset>(7),
        r.GetFieldValue<DateTimeOffset>(8));

    /// <summary>Neutralise les jokers LIKE saisis par l'utilisateur (% _ \).</summary>
    private static string EscapeLike(string value) =>
        value.Replace("\\", "\\\\").Replace("%", "\\%").Replace("_", "\\_");
}
