# Integrações

Todas as integrações seguem o mesmo contrato (`integrations/base.py`):

- `status()` → `Conectado` ou **`Não conectado` + lista do que falta**;
- `fetch_products()` → leitura oficial (levanta `NotConfigured` sem credencial);
- `prepare_listing()` → **rascunho**, nunca publicação;
- `evaluate_listing()` → checagens objetivas de título/descrição/preço;
- fallback garantido em CSV (`integrations/generic_csv.py`).

Nada é simulado. Sem credencial, nenhuma chamada de rede é feita.

## Shopee — Open Platform v2

| Item | Valor |
|---|---|
| Documentação | https://open.shopee.com/documents |
| Variáveis | `SHOPEE_PARTNER_ID`, `SHOPEE_PARTNER_KEY`, `SHOPEE_SHOP_ID` |
| Assinatura | `sha256(partner_key, partner_id + path + timestamp + access_token + shop_id)` |
| Leitura implementada | `/api/v2/product/get_item_list` |
| Escrita | apenas rascunho (`/api/v2/product/add_item` proposto, exige aprovação) |
| Limite de título | 120 caracteres |

## Mercado Livre — OAuth 2.0

| Item | Valor |
|---|---|
| Documentação | https://developers.mercadolivre.com.br |
| Variáveis | `ML_CLIENT_ID`, `ML_CLIENT_SECRET`, `ML_REDIRECT_URI`, `ML_ACCESS_TOKEN`, `ML_REFRESH_TOKEN` |
| Fluxo | `authorization_url()` → `code` → `exchange_code()` (tokens vão para o `.env`) |
| Leitura | `/users/me`, `/users/{id}/items/search`, busca pública `/sites/MLB/search` |
| Escrita | rascunho `/items`; publicar exige aprovação `publish_listing` |
| Limite de título | 60 caracteres |

A busca pública (`search_market`) já serve para concorrência **sem token**.

## TikTok Shop — Open API v2

| Item | Valor |
|---|---|
| Documentação | https://partner.tiktokshop.com/doc |
| Variáveis | `TIKTOK_APP_KEY`, `TIKTOK_APP_SECRET`, `TIKTOK_ACCESS_TOKEN`, `TIKTOK_SHOP_CIPHER` |
| Assinatura | HMAC-SHA256(secret, path + params ordenados + body) |
| Leitura | `/product/202309/products/search` |
| Limite de título | 255 caracteres |

## Instagram — Meta Graph API

| Item | Valor |
|---|---|
| Documentação | https://developers.facebook.com/docs/instagram-platform |
| Variáveis | `INSTAGRAM_ACCESS_TOKEN`, `INSTAGRAM_BUSINESS_ID` |
| Permissões | `instagram_basic`, `instagram_content_publish`, `pages_show_list` |
| Leitura | `/{ig-user-id}/media` (legenda, curtidas, comentários, permalink) |
| Publicação | `prepare_post()` cria rascunho; publicar exige aprovação |

## WooCommerce / loja própria — REST v3

| Item | Valor |
|---|---|
| Documentação | https://woocommerce.github.io/woocommerce-rest-api-docs/ |
| Variáveis | `WOOCOMMERCE_URL`, `WOOCOMMERCE_CONSUMER_KEY`, `WOOCOMMERCE_CONSUMER_SECRET` |
| Leitura | `/products`, `/orders` |
| Escrita | `update_price()` — somente após aprovação `price_change` |
| Limite de título | 200 caracteres |

## CSV (sempre disponível)

Entidades aceitas: `products`, `competitors`, `suppliers`, `sales`,
`opportunities`. Cabeçalhos em português são reconhecidos (`nome`, `preço`,
`custo`, `preco_compra`, `custo_extra`, `avaliacao`, `prazo_dias`…).

- Separador `;` ou `,` detectado automaticamente.
- Valores como `R$ 1.234,56` são convertidos.
- Linha sem campo obrigatório é **rejeitada com o motivo**, nunca "consertada".
- `competitors.csv` precisa de `product_name` igual ao nome no catálogo.

Modelos prontos: `python -c "from integrations.generic_csv import template_csv; template_csv('products','exports/modelo.csv')"`
ou o botão "Baixar modelo CSV" em cada página.

## O que nenhuma integração faz

- Não burla CAPTCHA, login, limite de acesso ou proteção anti-robô.
- Não raspa páginas de marketplace para "inventar" volume de vendas.
- Não publica, não compra e não paga sem aprovação registrada.
