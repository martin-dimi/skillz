# Project Structure

Template for spinning up a TypeScript monorepo with an RN/Expo mobile app, backend and a webapp.

BEFORE SPINNING THINGS UP, ensure you have up to date documentation of all the libraries. 
USE their documentation to spin them up. REMOVE unneded boilerplate 

## Monorepo

**Bun workspaces**. Everything app-specific lives under `apps/*`. 
The root holds only workspace config, lint config and a shared TS base.

```
project-root/
├── apps/
│   ├── mobile/      <- Expo app (React Native)
│   ├── webapp/      <- Tanstack Start + Vite + Tailwind + Shadcn
│   ├── server/      <- Bun + Hono API
│   └── shared/      <- types, utils, constants used by more than one app.
├── package.json     <- workspaces: ["apps/*"], devDeps only (biome, ts, @types/bun)
├── tsconfig.json    <- strict base; packages extend or override
├── biome.json       <- single lint/format config for the repo
└── bun.lock
```

### Conventions

- **App names**: scoped + private, e.g. `@<project-name>/mobile`, `@<project-name>/server`, `@<project-name>/shared`, etc.
- **Cross-package deps**: `"@<project-name>/shared": "workspace:*"`.
- **Intra-package imports**: `@/*` alias to the package root. No `../../` across folders. (no relative imports)
- **Filenames**: lowercase, one component / screen / endpoint per file. Private sub-components tightly coupled to a parent may live in the same file (main export at top, helpers below).
- **Scaffolding**: always start each package with its official CLI (`create-expo-app`, `bun create hono`), then strip the boilerplate. Never hand-roll.

### Tooling

| | |
|--|--|
| Runtime | Bun |
| Lint/Format | Biome (one config at root, tab indent, double quotes) |
| TS | Strict, `moduleResolution: bundler`, `noEmit`, `verbatimModuleSyntax` |
| Root scripts | `bun check` (dry) / `bun fix` (write) |

## shared/

Framework-agnostic code consumed by both mobile and server. No build step - direct `.ts` imports via the `exports` map.

```
apps/shared/
├── types/        <- domain types and zod schemas
├── lib/          <- pure helpers, no React, no Bun, no RN
├── constants.ts
├── package.json  <- exports: ./types/*, ./lib/*, ./constants
└── tsconfig.json
```

Imported as `@project/shared/lib/foo`, `@project/shared/types/bar`.

## server/

Bun + Hono. Internally split into its own mini-monorepo of domain packages wired together by `main.ts`.

```
apps/server/
├── main.ts         <- orchestrator: build env → db → server → services, then start
├── pkgs/
│   ├── db/         <- db client, migration.ts, migrations/* (up + down)
│   ├── server/     <- Hono instance, common middleware, health.ts
│   └── <domain>/   <- one pkg per domain (e.g. users, quests, uploads)
│       ├── db.ts       <- domain's db queries
│       ├── routes.ts   <- registers its own routes on the server
│       └── *.ts        <- logic split into files by responsibility
├── lib/
│   ├── log.ts      <- shared logger
│   └── env.ts      <- typed env parsing
├── Dockerfile
└── package.json    <- dev: bun run --hot --env-file=.env main.ts
```

### Dependency injection

Use dep injections. `main.ts` constructs each piece and passes it to whoever needs it.
Tho logger can be considered more global (pino)

```ts
const env = loadEnv();
const db = createDb(env);
await runMigrations(db);
const server = createServer();

createUsersServcie({ db, server });
createQuestsService({ db, server, users });  // service-on-service deps are explicit

server.listen(env.PORT);
```

Each domain pkg exports a `create*Service` function that takes its dependencies, attaches routes to the server and exposes whatever the rest of the app needs. Domains never reach for a shared singleton; if they need something, it's an argument.

### API types: Hono RPC

Server exports its app type, clients import it as a **type-only** dependency:

```ts
// apps/server/main.ts
export type AppType = typeof app;

// mobile / webapp
import type { AppType } from "@<project>/server";
const client = hc<AppType>(API_BASE);
```

End-to-end type safety with no codegen and nothing from the server bundle ships to the client. Validation stays on the server (zod via `@hono/zod-validator`); any schemas a client also needs at runtime go in `shared/`.

### API types: Hono RPC

Server exports its app type, mobile imports it as a **type-only** dependency:

```ts
// server/index.ts
export type AppType = typeof app;

// mobile
import type { AppType } from "@project/server";
const client = hc<AppType>(API_BASE);
```

End-to-end type safety with no codegen and nothing from the server bundle ships to the client. Validation stays on the server (zod via `@hono/zod-validator`); any schemas the client also needs at runtime go in `shared/`.

## mobile/

Expo app. Standard Expo layout at the package root (`app.json`, `babel.config.js`, `metro.config.js`, `ios/`, `android/`, `assets/`); all source under `src/`.

```
apps/mobile/src/
├── app/             <- Expo Router routes (file-based)
│   ├── _layout.tsx
│   ├── onboarding/***      
│   └── settings.tsx
├── features/        <- domain modules, self-contained vertical slices
│   └── <feature>/
│       ├── store.ts    <- Zustand store
│       ├── api.ts      <- server calls
│       ├── db.ts       <- local persistence queries
│       ├── hooks.ts    <- React hooks combining the above
│       └── index.ts    <- public surface
├── components/      <- reusable UI, grouped by domain (ui/, brand/, home/, ...)
├── hooks/           <- more general hooks (useMotion, useDebounce, etc)
├── lib/             <- utils, helpers
├── providers/       <- React context providers (posthog, storage, etc)
├── storage/         <- MMKV / SQLite layer
├── api/             <- HTTP client (one fetch wrapper, or hc<AppType>)
└── global.css       <- Uniwind/Tailwind entrypoint
```

### Routing

Expo Router (file-based). Folder = route, `(group)` = grouping without URL segment, `_layout.tsx` = nested layout. Mirrors Next.js app router.

### Features

Each feature is a vertical slice. Screens and components import from features; features never import from screens. 

### Styling - Uniwind (Tailwind v4 for React Native)

- Deps: `tailwindcss`, `uniwind`, `tailwind-merge`
- Global stylesheet at `src/global.css` with `@import 'uniwind'`
- Wired through `metro.config.js` (`withUniwind`) and `babel.config.js`
- Usage: `className="flex-1 bg-background"` on RN components - never `style={{}}`
- Theme tokens via CSS variables in `@theme`; OKLCH colour space with semantic names
- Variants: `dark:`, `ios:`, `android:`, `sm:/md:/lg:`, `data-[state=open]:`
- Compound font weights/styles use separate classes: `font-sans font-bold`, not `font-sans-bold`
- use impeccable skill to design

### Path alias

`@/*` resolves to the mobile package root (`@/src/features/foo`).
`feat/*` resolves to `src/features/*` (`feat/foo` → `src/features/foo`).
`ui/*` resolves to `src/components/ui/*` 


## webapp/
- Core components are installed through shadcn (bunx shadcn install) and styled appropriately afterwards
- Limit custom code as much as possible. Components need to be as reusable as possible
- Don't bother with server side rendering too much.

### Structure
```
apps/webapp/
├── features/           <- domain modules, self-contained vertical slices
│   └── <feature>/
│       ├── store.ts    <- Zustand store
│       ├── api.ts      <- server api calls (using common lib/api.ts client)
│       ├── hooks.ts    <- React hooks combining the above api calls
│       ├── types.ts    <- Common types for this feature. If shared with backend they should live in apps/shared/types/
│       ├── lib.ts      <- Common helper or util functions for this feature
│       └── components/ <- common components for this feature. Can be importent from anywhere
└── package.json        <- 
```

### Styling
- We use tailwind for styling and rely on shadcn for default ui components (we can style on top).
- Use impeccable skill to create and work on the UI side like pages, components, etc. (this is our designer)

### SUPER IMPORTANT
Every word and element needs to earn it's place. Everything has meaning and purpose. we do not put elements or words for the sake of it.
This gives us polish and professionalism which is #1 priority to building good UI/UX. 
Everything has it's place, once it's not needed it should move out the way.
