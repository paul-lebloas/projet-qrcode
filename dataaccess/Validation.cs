namespace DataAccess;

public static class Ean13Validator
{
    /// <summary>13 chiffres avec clé de contrôle EAN-13 valide.</summary>
    public static bool IsValid(string? value)
    {
        if (value is null || value.Length != 13)
        {
            return false;
        }

        var sum = 0;
        for (var i = 0; i < 13; i++)
        {
            var c = value[i];
            if (c < '0' || c > '9')
            {
                return false;
            }

            if (i < 12)
            {
                var digit = c - '0';
                sum += i % 2 == 0 ? digit : digit * 3;
            }
        }

        return (10 - sum % 10) % 10 == value[12] - '0';
    }
}

public static class ProductValidation
{
    public static (ProductInput? Value, Dictionary<string, string[]>? Errors) Validate(ProductInput? input)
    {
        var errors = new Dictionary<string, string[]>();
        if (input is null)
        {
            errors["body"] = ["Corps de requête JSON manquant."];
            return (null, errors);
        }

        var ean = Clean(input.Ean13);
        var qr = Clean(input.QrCode);
        var name = Clean(input.Name);
        var brand = Clean(input.Brand);
        var category = Clean(input.Category);
        var description = Clean(input.Description);

        if (name is null)
        {
            errors["name"] = ["Le nom est obligatoire."];
        }
        else if (name.Length > 200)
        {
            errors["name"] = ["Le nom ne doit pas dépasser 200 caractères."];
        }

        if (ean is null && qr is null)
        {
            errors["identifier"] = ["Au moins un identifiant est requis : ean13 ou qr_code."];
        }

        if (ean is not null && !Ean13Validator.IsValid(ean))
        {
            errors["ean13"] = ["EAN-13 invalide : 13 chiffres avec clé de contrôle correcte attendus."];
        }

        if (qr is { Length: > 2048 })
        {
            errors["qr_code"] = ["Le contenu du QR Code ne doit pas dépasser 2048 caractères."];
        }

        if (brand is { Length: > 100 })
        {
            errors["brand"] = ["La marque ne doit pas dépasser 100 caractères."];
        }

        if (category is { Length: > 100 })
        {
            errors["category"] = ["La catégorie ne doit pas dépasser 100 caractères."];
        }

        if (description is { Length: > 2000 })
        {
            errors["description"] = ["La description ne doit pas dépasser 2000 caractères."];
        }

        return errors.Count > 0
            ? (null, errors)
            : (new ProductInput(ean, qr, name, brand, category, description), null);
    }

    private static string? Clean(string? value)
    {
        var trimmed = value?.Trim();
        return string.IsNullOrEmpty(trimmed) ? null : trimmed;
    }
}
