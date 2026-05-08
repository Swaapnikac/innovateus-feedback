import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// Server-side gate for the obscured admin area. Without this, navigating
// directly to /iu-ops-9k2p/dashboard while logged out briefly served the
// admin page bundle before a client-side 401 redirect kicked in. Now the
// middleware short-circuits at the edge: if the relevant auth cookie is
// missing, we redirect to the matching login page before any admin UI
// code is sent to the browser.
//
// The httpOnly admin_token / editor_token cookies are set by the API on
// successful login. Middleware runs on the server, so it CAN read them
// even though browser-side JS cannot. This is the entire reason we moved
// off the localStorage token: the server can enforce auth before render,
// the client cannot.

const ADMIN_LOGIN = "/iu-ops-9k2p/login";
const EDITOR_LOGIN = "/iu-ops-9k2p/editor/login";

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  // Editor routes accept either an editor or an admin cookie (admins can
  // also edit). The login page itself is obviously exempt.
  if (pathname.startsWith("/iu-ops-9k2p/editor")) {
    if (pathname === EDITOR_LOGIN) return NextResponse.next();
    const editorCookie = req.cookies.get("editor_token")?.value;
    const adminCookie = req.cookies.get("admin_token")?.value;
    if (!editorCookie && !adminCookie) {
      const url = req.nextUrl.clone();
      url.pathname = EDITOR_LOGIN;
      return NextResponse.redirect(url);
    }
    return NextResponse.next();
  }

  // Everything else under /iu-ops-9k2p/* requires the manager cookie.
  if (pathname.startsWith("/iu-ops-9k2p")) {
    if (pathname === ADMIN_LOGIN) return NextResponse.next();
    const adminCookie = req.cookies.get("admin_token")?.value;
    if (!adminCookie) {
      const url = req.nextUrl.clone();
      url.pathname = ADMIN_LOGIN;
      return NextResponse.redirect(url);
    }
  }

  return NextResponse.next();
}

export const config = {
  // Limit the matcher to admin routes so middleware overhead stays off the
  // public learner survey pages.
  matcher: ["/iu-ops-9k2p/:path*"],
};
