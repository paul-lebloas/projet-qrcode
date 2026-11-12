-- Schéma PostgreSQL et données de démonstration.
-- Exécuté une seule fois, à l'initialisation du volume `pgdata`.
-- Les produits ci-dessous sont fictifs ; les EAN-13 ont une clé de contrôle valide.

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS products (
    id          BIGSERIAL PRIMARY KEY,
    ean13       TEXT UNIQUE CHECK (ean13 ~ '^[0-9]{13}$'),
    qr_code     TEXT UNIQUE CHECK (length(qr_code) BETWEEN 1 AND 2048),
    name        TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 200),
    brand       TEXT CHECK (length(brand) <= 100),
    category    TEXT CHECK (length(category) <= 100),
    description TEXT CHECK (length(description) <= 2000),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT product_has_identifier CHECK (ean13 IS NOT NULL OR qr_code IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS products_name_trgm  ON products USING gin (name  gin_trgm_ops);
CREATE INDEX IF NOT EXISTS products_brand_trgm ON products USING gin (brand gin_trgm_ops);

INSERT INTO products (ean13, qr_code, name, brand, category, description) VALUES
  ('3760000000017', 'https://produits.example/p/1001', 'Biscuits sablés pur beurre 200 g', 'Maison Démo', 'Épicerie sucrée', 'Sablés au beurre doux, cuisson lente.'),
  ('3760000000024', 'https://produits.example/p/1002', 'Café moulu arabica 250 g', 'Torréfaction Démo', 'Boissons chaudes', 'Pur arabica, torréfaction moyenne.'),
  ('3760000000031', 'https://produits.example/p/1003', 'Jus de pomme pressé 1 L', 'Vergers Démo', 'Boissons', 'Jus de pomme 100 % pur jus, sans sucres ajoutés.'),
  ('3760000000048', 'https://produits.example/p/1004', 'Pâtes complètes torsades 500 g', 'Pasta Démo', 'Épicerie salée', 'Blé dur complet, 3 min de plus de cuisson.'),
  ('3760000000055', 'https://produits.example/p/1005', 'Chocolat noir 70 % 100 g', 'Cacao Démo', 'Épicerie sucrée', 'Tablette de chocolat noir, cacao d''origine unique.'),
  ('3760000000062', 'https://produits.example/p/1006', 'Yaourt nature bio 4 x 125 g', 'Laiterie Démo', 'Produits laitiers', 'Yaourt au lait entier bio.'),
  ('3760000000079', 'https://produits.example/p/1007', 'Lentilles vertes 500 g', 'Terroir Démo', 'Légumes secs', 'Lentilles vertes cultivées en France.'),
  ('3760000000086', NULL, 'Huile d''olive vierge extra 50 cl', 'Oliveraie Démo', 'Huiles', 'Première pression à froid.'),
  ('3760000000093', NULL, 'Muesli croustillant 375 g', 'Matin Démo', 'Petit-déjeuner', 'Flocons d''avoine, noisettes et miel.'),
  ('3760000000109', NULL, 'Thé vert au jasmin 20 sachets', 'Théière Démo', 'Boissons chaudes', 'Thé vert parfumé à la fleur de jasmin.')
ON CONFLICT DO NOTHING;
