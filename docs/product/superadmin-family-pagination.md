# Superadmin family directory pagination

Issue: #205 (roadmap #223)

## Compatibility contract

`GET /api/superadmin/families/` keeps the existing array response when neither `limit` nor `offset` is supplied. This preserves the current Superadmin PWA while server-side pagination is adopted by the frontend in a later bounded slice.

When either pagination parameter is present, the endpoint returns:

- `count`: total rows after search/status filtering
- `limit`: requested page size (default `100`, maximum `200`)
- `offset`: zero-based offset
- `sort`: validated server-side sort key
- `status`: validated status filter or `null`
- `results`: only the requested family rows

Search, status filtering and sorting happen before `count` and slicing.

## Validation

Pagination fails closed with HTTP 400 for non-integer values, `limit < 1`, `limit > 200` or negative offsets. Existing status and sort allow-lists remain unchanged.

## Performance

Only the sliced page is passed into the family-directory priming layer added by the #205 query-budget work. Entitlement resolution and invitation delivery health are therefore calculated only for returned tenants rather than the entire filtered directory.

The response fields of each family row and all privacy boundaries remain unchanged. No private family content is queried or serialized.
