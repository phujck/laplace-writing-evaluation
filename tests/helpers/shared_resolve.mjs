// A Node module resolve hook for source tests (repair2 R4): the browser serves src/laplace/web/static_shared/
// at /shared/, so a module importing '/shared/x.mjs' resolves to that file here. Register it before the
// first dynamic import:  register('./helpers/shared_resolve.mjs', import.meta.url)
const shared = new URL('../../src/laplace/web/static_shared/', import.meta.url);
export async function resolve(specifier, context, next) {
  if (specifier.startsWith('/shared/')) return next(new URL(specifier.slice('/shared/'.length), shared).href, context);
  return next(specifier, context);
}
