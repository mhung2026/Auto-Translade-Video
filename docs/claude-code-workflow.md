# 🎓 Vibe Coding Với Claude Code — Hướng Dẫn Toàn Diện

> Tài liệu giảng dạy quy trình làm việc với Claude Code cho **mọi loại dự án**: web app, mobile, API backend, CLI tool, data pipeline, automation script...
>
> Triết lý: bạn không cần biết code chi tiết — bạn cần biết **mô tả vấn đề rõ ràng**, **tổ chức dự án đúng** và **giao tiếp với AI hiệu quả**.

---

## 📚 Mục Lục

1. [Vibe Coding là gì?](#1-vibe-coding-là-gì)
2. [Cấu trúc thư mục chuẩn cho mọi dự án](#2-cấu-trúc-thư-mục-chuẩn-cho-mọi-dự-án)
3. [Setup Claude Code lần đầu](#3-setup-claude-code-lần-đầu)
4. [Plugins, Skills & MCP — chọn theo loại dự án](#4-plugins-skills--mcp--chọn-theo-loại-dự-án)
5. [Cách prompt Claude Code hiệu quả](#5-cách-prompt-claude-code-hiệu-quả)
6. [Quy trình khởi tạo dự án từ Zero → Hero](#6-quy-trình-khởi-tạo-dự-án-từ-zero--hero)
7. [Quy trình làm việc hàng ngày](#7-quy-trình-làm-việc-hàng-ngày)
8. [Ví dụ thực tế theo loại dự án](#8-ví-dụ-thực-tế-theo-loại-dự-án)
9. [Checklist & cheatsheet](#9-checklist--cheatsheet)
10. [Xử lý tình huống thường gặp](#10-xử-lý-tình-huống-thường-gặp)

---

## 1. Vibe Coding Là Gì?

### 1.1. Định nghĩa

**Vibe coding** = phong cách lập trình mới: bạn **mô tả ý đồ** (vibe), AI **viết code**.

Bạn không cần thuộc cú pháp — bạn cần biết:
- **Mình muốn gì** (clarity)
- **Tổ chức công việc thế nào** (structure)
- **Giao việc cho AI ra sao** (communication)
- **Kiểm tra kết quả thế nào** (verification)

### 1.2. Claude Code khác gì ChatGPT?

| ChatGPT / AI Chat thường | Claude Code |
|---|---|
| Bạn copy-paste code qua lại | Claude tự đọc/sửa file trong dự án |
| Mất context khi đổi chat | Có **CLAUDE.md** + **memory** ghi nhớ |
| Không chạy được lệnh | Chạy `npm install`, `git`, test... |
| Không biết dự án bạn | Hiểu cấu trúc, tự tìm file liên quan |
| Trả lời 1 lần | Lặp: đọc → sửa → chạy → kiểm → fix |

➡️ **Hệ quả quan trọng**: bạn phải **tổ chức dự án có kỷ luật** để Claude đọc hiểu được. Dự án càng hỗn loạn, AI càng làm sai.

### 1.3. Ba nguyên tắc cốt lõi của vibe coding

#### 🥇 Nguyên tắc 1: **Spec trước, code sau**
> "Đo hai lần, cắt một lần"

Đừng nói: "làm cho tao cái app todo".
Hãy nói: "đọc spec ở `docs/specs/todo-app.md`, lập plan, hỏi tôi điểm nào chưa rõ trước khi code".

#### 🥈 Nguyên tắc 2: **Tách biệt các vùng**
- `code` ≠ `docs` ≠ `data` ≠ `output`
- Mỗi vùng 1 thư mục riêng → Claude không nhầm lẫn

#### 🥉 Nguyên tắc 3: **Kiểm tra trước khi tin**
- Claude báo "Done!" ≠ thật sự xong
- Luôn yêu cầu Claude **chứng minh** bằng output lệnh, screenshot, test pass

---

## 2. Cấu Trúc Thư Mục Chuẩn Cho Mọi Dự Án

### 2.1. Khung xương chung — áp dụng cho 90% dự án

```
my-project/
├── .claude/                    # ⚙️ Cấu hình Claude Code dự án
│   ├── settings.json           #    Settings team (commit)
│   ├── settings.local.json     #    Settings cá nhân (KHÔNG commit)
│   └── skills/                 #    Custom skills riêng dự án
│
├── docs/                       # 📖 NÃO CỦA DỰ ÁN — quan trọng nhất
│   ├── specs/                  #    Cái GÌ phần mềm phải làm
│   ├── plans/                  #    Cách LÀM — Claude viết, bạn duyệt
│   ├── adr/                    #    Quyết định kiến trúc + lý do (tùy chọn)
│   └── api/                    #    Tài liệu API (nếu có backend)
│
├── src/                        # 💻 SOURCE CODE
│   ├── ...                     #    Cấu trúc tùy stack (xem 2.3)
│
├── tests/                      # 🧪 Test mirror cấu trúc src/
│
├── public/ hoặc static/        # 🖼️ Asset tĩnh (web app)
├── scripts/                    # 🔧 Script tiện ích (build, deploy, seed)
│
├── data/ hoặc input/           # 📥 Dữ liệu đầu vào (.gitignore nếu lớn)
├── output/ hoặc dist/          # 📤 Build/kết quả (.gitignore)
├── logs/                       # 📝 Log chạy (.gitignore)
│
├── CLAUDE.md                   # 🤖 Hướng dẫn Claude — BẮT BUỘC
├── README.md                   # 👋 Người mới đọc đầu tiên
├── .env.example                # 🔐 Template biến môi trường
├── .gitignore
└── [package.json | requirements.txt | go.mod | Cargo.toml | ...]
```

### 2.2. Vai trò từng thư mục — chi tiết

#### 📖 `docs/` — Não bộ dự án (QUAN TRỌNG NHẤT)

> Nếu chỉ chọn 1 thư mục để đầu tư công sức → chọn `docs/`. Đây là nơi Claude đọc để hiểu dự án.

| Subfolder | Nội dung | Ai viết | Khi nào |
|---|---|---|---|
| `specs/` | Đặc tả: yêu cầu, user story, ràng buộc, ví dụ input/output | Bạn (hoặc Claude phỏng vấn bạn) | Trước khi code |
| `plans/` | Kế hoạch: bước 1, 2, 3... file nào sửa, test nào viết | Claude (bạn duyệt) | Sau spec, trước code |
| `adr/` | Architecture Decision Record: "tại sao chọn X thay vì Y" | Bạn + Claude | Khi quyết định lớn |
| `api/` | Tài liệu API endpoint (REST/GraphQL) | Sinh tự động hoặc Claude viết | Sau khi có API |

**Quy tắc đặt tên**: `001-feature-name.md`, `002-feature-name.md` → tra cứu dễ.

#### 💻 `src/` — Code logic, không có gì khác

- **KHÔNG** để config, data, output, log ở đây
- **KHÔNG** để file CLI/entry point lớn ở đây
- Mỗi module 1 trách nhiệm rõ ràng

#### 🧪 `tests/` — Phản chiếu `src/`

- Mỗi `src/foo.js` → có `tests/foo.test.js`
- Test là **tài liệu sống**: đọc test biết module hoạt động ra sao

#### 🤖 `CLAUDE.md` — File mà Claude tự đọc

> **File này quyết định 50% chất lượng Claude làm việc.** Đầu tư viết kỹ.

#### 📥📤 `data/` vs `output/`

- **Đầu vào** vs **đầu ra** — đừng trộn lẫn
- Luôn `gitignore` `output/` (build artifact, kết quả lớn)

### 2.3. Biến thể theo stack

#### 🌐 Web App — React/Next.js

```
src/
├── app/ hoặc pages/        # Routes (Next.js)
├── components/             # React components tái sử dụng
│   ├── ui/                 # Button, Input, Card... (primitives)
│   └── features/           # Component nghiệp vụ (LoginForm, ProductCard)
├── hooks/                  # Custom React hooks
├── lib/ hoặc utils/        # Helper, không phụ thuộc React
├── services/ hoặc api/     # Gọi API backend
├── stores/                 # State management (Zustand, Redux...)
├── styles/                 # Global CSS, theme
└── types/                  # TypeScript types/interfaces
```

#### 🔌 Backend API — Node/Express, FastAPI, Go...

```
src/
├── routes/ hoặc controllers/   # HTTP handlers
├── services/                   # Business logic
├── models/ hoặc entities/      # Data models, ORM entities
├── repositories/               # Data access layer
├── middleware/                 # Auth, logging, validation
├── utils/                      # Helper
└── config/                     # Cấu hình
```

#### 📱 Mobile — React Native, Flutter

```
src/ hoặc lib/
├── screens/ hoặc views/        # Màn hình
├── components/                 # Component tái sử dụng
├── navigation/                 # Routing
├── services/                   # API calls
├── stores/                     # State
└── assets/                     # Hình ảnh, font
```

#### 🤖 CLI Tool / Script

```
src/                            # Logic chính
├── commands/                   # Mỗi subcommand 1 file
├── core/                       # Logic cốt lõi
└── utils/

bin/ hoặc cli.js                # Entry point CLI
```

#### 📊 Data Pipeline / ML

```
src/
├── ingest/                     # Thu thập dữ liệu
├── process/                    # Xử lý
├── models/                     # ML models (nếu có)
└── export/                     # Xuất kết quả

data/
├── raw/                        # Dữ liệu thô
├── processed/                  # Đã xử lý
└── reference/                  # Lookup tables

notebooks/                      # Jupyter (nếu có)
```

### 2.4. Mẫu `CLAUDE.md` — copy & sửa cho dự án của bạn

```markdown
# Hướng dẫn Claude Code

## Dự án này làm gì
[1-3 câu mô tả]

Ví dụ: "App quản lý task team nhỏ. Backend FastAPI + Postgres, frontend Next.js.
Người dùng tạo project, mời member, assign task, theo dõi tiến độ."

## Tech Stack
- **Backend**: Python 3.12, FastAPI, SQLAlchemy, Postgres 16
- **Frontend**: Next.js 15, TypeScript, Tailwind, shadcn/ui
- **Test**: pytest (backend), Vitest + Playwright (frontend)
- **Deploy**: Docker + Railway

## Cấu trúc dự án
- `docs/specs/` — đặc tả tính năng, ĐỌC TRƯỚC khi code
- `docs/plans/` — kế hoạch triển khai từng feature
- `backend/` — API server
- `frontend/` — Next.js app
- `infra/` — Dockerfile, docker-compose, deploy config

## Quy ước code
- Backend: type hints đầy đủ, dùng Pydantic v2 cho validation
- Frontend: components dùng named export, không default export
- Database: migration qua Alembic, KHÔNG sửa schema thủ công
- Naming: snake_case (Python), camelCase (TS)
- Git: Conventional Commits (feat/fix/docs/refactor/test/chore)

## Lệnh thường dùng
- Dev backend: `cd backend && uvicorn app.main:app --reload`
- Dev frontend: `cd frontend && pnpm dev`
- Test backend: `cd backend && pytest`
- Test frontend: `cd frontend && pnpm test`
- Migration: `cd backend && alembic upgrade head`
- Lint: `pnpm lint` (frontend), `ruff check .` (backend)

## File quan trọng đọc trước
- `docs/specs/001-architecture.md` — kiến trúc tổng
- `backend/app/config.py` — config tập trung
- `backend/app/db/base.py` — base ORM
- `frontend/src/lib/api.ts` — client API

## Đừng làm
- Đừng commit file trong `output/`, `node_modules/`, `.next/`
- Đừng sửa file migration cũ — luôn tạo migration mới
- Đừng tạo file `*.md` mới trừ khi tôi yêu cầu
- Đừng dùng `any` trong TypeScript
- Đừng hardcode URL/secret — dùng `.env`

## Khi gặp lỗi build/test
1. Đọc full error trace
2. Đọc code dòng gây lỗi
3. ĐỪNG đoán — chứng minh giả thuyết bằng code/log
4. Fix root cause, không workaround

## Memory dài hạn
Tôi prefer:
- Chạy test với output verbose: `pytest -xvs`
- Pull request có screenshot UI nếu đổi frontend
- Migration phải có rollback
```

### 2.5. Ví dụ trực quan — dự án web app TODO list

```
todo-webapp/
├── .claude/
│   ├── settings.json
│   └── skills/
│
├── docs/
│   ├── specs/
│   │   ├── 001-product-spec.md          # Mô tả app
│   │   ├── 002-auth-flow.md              # Đăng ký/đăng nhập
│   │   └── 003-realtime-sync.md          # Sync WebSocket
│   ├── plans/
│   │   ├── 001-init-project.md
│   │   ├── 002-implement-auth.md
│   │   └── 003-todo-crud.md
│   └── adr/
│       └── 001-why-postgres-over-mongo.md
│
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── routers/
│   │   ├── services/
│   │   ├── models/
│   │   └── db/
│   ├── tests/
│   ├── alembic/                          # Migrations
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   │   ├── app/                          # Next.js routes
│   │   ├── components/
│   │   ├── lib/
│   │   └── hooks/
│   ├── tests/
│   ├── public/
│   └── package.json
│
├── infra/
│   ├── Dockerfile.backend
│   ├── Dockerfile.frontend
│   └── docker-compose.yml
│
├── CLAUDE.md
├── README.md
├── .env.example
└── .gitignore
```

---

## 3. Setup Claude Code Lần Đầu

### 3.1. Cài đặt CLI

```bash
# macOS / Linux
curl -fsSL https://claude.ai/install.sh | sh

# Windows (PowerShell)
iwr -useb https://claude.ai/install.ps1 | iex

# Hoặc qua npm (mọi OS)
npm install -g @anthropic-ai/claude-code
```

### 3.2. Đăng nhập

```bash
claude login
```

### 3.3. IDE Extension (khuyến nghị)

- **VS Code**: cài extension "Claude Code" từ Marketplace
- **JetBrains** (IntelliJ, PyCharm, WebStorm...): cài plugin "Claude Code"
- **Cursor / Windsurf**: tích hợp sẵn

➡️ Khi mở file trong IDE, Claude tự biết bạn đang xem gì.

### 3.4. Ba cấp độ Settings

```
~/.claude/settings.json                  ← TOÀN MÁY (cá nhân, mọi dự án)
<project>/.claude/settings.json          ← DỰ ÁN (chia sẻ team — commit)
<project>/.claude/settings.local.json    ← DỰ ÁN (riêng bạn — KHÔNG commit)
```

**Settings cá nhân khuyến nghị** (`~/.claude/settings.json`):

```json
{
  "autoUpdatesChannel": "latest",
  "effortLevel": "max",
  "enabledPlugins": {
    "superpowers@claude-plugins-official": true,
    "context7@claude-plugins-official": true,
    "code-review@claude-plugins-official": true,
    "feature-dev@claude-plugins-official": true,
    "skill-creator@claude-plugins-official": true
  }
}
```

**Giải thích**:
- `effortLevel: "max"` — Claude suy nghĩ kỹ hơn (tốn token nhưng chất lượng tăng)
- `autoUpdatesChannel: "latest"` — luôn lấy bản mới nhất
- ⚠️ **Tránh** `skipDangerousModePermissionPrompt: true` trừ khi hiểu rõ rủi ro

### 3.5. `.gitignore` mẫu (mọi dự án)

```gitignore
# Claude — KHÔNG commit settings cá nhân
.claude/settings.local.json

# Output / build / cache
output/
dist/
build/
.next/
.nuxt/
.cache/
node_modules/
__pycache__/
*.pyc
.pytest_cache/
.venv/
venv/

# Logs
*.log
logs/

# Env / secret
.env
.env.local
.env.*.local

# IDE
.vscode/
.idea/
*.swp
.DS_Store

# Dependency lock (tùy quy ước team)
# package-lock.json hoặc yarn.lock — thường COMMIT
```

---

## 4. Plugins, Skills & MCP — Chọn Theo Loại Dự Án

### 4.1. Plugins phổ thông — cài cho MỌI dự án

| Plugin | Tại sao cần | Lệnh |
|---|---|---|
| **superpowers** ⭐⭐⭐ | TDD, debug, brainstorm có hệ thống. Bộ skill khung xương | `/plugin install superpowers@claude-plugins-official` |
| **context7** ⭐⭐⭐ | Tra docs library realtime (React, Vue, FastAPI, Django...) | `/plugin install context7@claude-plugins-official` |
| **code-review** ⭐⭐ | Review trước khi merge PR | `/plugin install code-review@claude-plugins-official` |
| **feature-dev** ⭐⭐ | Multi-agent dev cho feature lớn | `/plugin install feature-dev@claude-plugins-official` |
| **skill-creator** ⭐ | Tự tạo skill cho dự án | `/plugin install skill-creator@claude-plugins-official` |

### 4.2. Plugins theo loại dự án

| Loại dự án | Plugin nên cài |
|---|---|
| 🌐 **Web app frontend** | `frontend-design`, `playwright`, `figma`, `typescript-lsp` |
| 🔌 **Backend API** | `code-review`, `security-guidance` |
| 📱 **Mobile** | `figma`, `typescript-lsp` (RN), |
| 🎨 **Có designer** | `figma` |
| 🔒 **Bảo mật quan trọng** | `security-guidance` |
| 🧪 **Cần test E2E** | `playwright` |

### 4.3. Skills — kỹ năng chuyên biệt

**Skills có sẵn từ `superpowers`** (tự động dùng khi cần):

| Skill | Khi nào kích hoạt |
|---|---|
| `brainstorming` | Trước mọi tính năng mới |
| `writing-plans` | Có spec rồi, cần plan |
| `executing-plans` | Đã có plan, vào session khác để thực thi |
| `test-driven-development` | Implement feature/bugfix |
| `systematic-debugging` | Gặp bug, test fail |
| `verification-before-completion` | Trước khi tuyên bố xong |
| `using-git-worktrees` | Cô lập feature work |
| `requesting-code-review` | Trước merge |

**Cách dùng**: gõ `/<skill-name>` hoặc Claude tự kích hoạt.

**Tạo skill custom cho dự án**: tạo `<project>/.claude/skills/my-skill/SKILL.md`:

```markdown
---
name: my-skill
description: Mô tả KHI NÀO dùng — Claude đọc dòng này để quyết định
---

# Hướng dẫn skill

[Nội dung chi tiết — Claude sẽ tuân theo]
```

**Ví dụ skill custom hữu ích**:
- `deploy-staging` — quy trình deploy lên staging của team
- `db-migration` — quy trình migration an toàn
- `release-checklist` — checklist trước khi release production

### 4.4. MCP — kết nối Claude với thế giới ngoài

MCP (Model Context Protocol) cho Claude truy cập tool ngoài: browser, database, design file, email...

**Setup MCP** trong `~/.claude.json`:

```json
{
  "mcpServers": {
    "chrome-devtools": {
      "type": "stdio",
      "command": "npx",
      "args": ["chrome-devtools-mcp@latest"]
    },
    "playwright": {
      "type": "stdio",
      "command": "npx",
      "args": ["@playwright/mcp@latest"]
    },
    "postgres": {
      "type": "stdio",
      "command": "npx",
      "args": ["@modelcontextprotocol/server-postgres", "postgresql://localhost/mydb"]
    }
  }
}
```

**MCP phổ biến theo nhu cầu**:

| Bạn cần | MCP |
|---|---|
| Test web app, screenshot | `chrome-devtools`, `playwright` |
| Đọc design Figma | `figma` (qua plugin) |
| Query database | `postgres`, `sqlite`, `mysql` |
| Tra docs library | `context7` (qua plugin) |
| Quản lý GitHub issue/PR | `github` |
| Đọc/gửi email | `gmail` |
| Đọc Notion docs | `notion` |
| File ngoài dự án | `filesystem` |

---

## 5. Cách Prompt Claude Code Hiệu Quả

### 5.1. Mô hình CTOR — khung prompt 4 phần

```
[C] CONTEXT     — Đang ở đâu, file nào, vấn đề gì
[T] TASK        — Việc cụ thể cần làm
[O] OUTPUT      — Kết quả mong đợi
[R] RESTRICTION — Ràng buộc (đừng X, phải Y)
```

**❌ Prompt tệ**:
> "Sửa lỗi đăng nhập"

**✅ Prompt tốt** (theo CTOR):
> [C] Trong `frontend/src/app/login/page.tsx`, khi user nhấn "Login" với email sai format, form vẫn submit và backend trả 422.
>
> [T] Validate email **trước khi submit** bằng zod schema. Hiển thị error message dưới input.
>
> [O] Sửa file login page + viết test trong `frontend/tests/login.test.tsx`. Chạy `pnpm test` confirm pass.
>
> [R] Đừng đổi UI hiện tại. Đừng thêm dependency mới — đã có zod trong package.json.

### 5.2. 8 mẫu prompt cho mọi giai đoạn

#### 📍 Mẫu 1 — Khám phá codebase mới (lần đầu mở dự án)

```
Tôi mới clone dự án này. Hãy:
1. Đọc README.md và CLAUDE.md
2. Liệt kê: dự án làm gì, tech stack, cách chạy local
3. Vẽ ASCII data flow chính
4. Chỉ ra 5 file quan trọng nhất tôi cần đọc trước
ĐỪNG sửa code.
```

#### 📍 Mẫu 2 — Brainstorm tính năng mới (KHÔNG code)

```
Tôi muốn thêm tính năng: [mô tả 1-2 câu].

Áp dụng skill `brainstorming`:
1. Hỏi tôi 5-10 câu để làm rõ yêu cầu
2. Sau khi tôi trả lời, tổng hợp thành spec ở `docs/specs/00X-feature-name.md`
3. Đợi tôi review trước khi sang plan
ĐỪNG VIẾT CODE.
```

#### 📍 Mẫu 3 — Lập plan từ spec

```
Đọc `docs/specs/003-realtime-chat.md`.

Áp dụng skill `writing-plans`:
1. Brainstorm 2-3 cách triển khai, so sánh
2. Đề xuất 1 phương án
3. Tạo `docs/plans/003-realtime-chat.md` gồm:
   - Tech approach (WebSocket vs SSE vs polling — chọn cái nào, tại sao)
   - Files cần tạo/sửa (liệt kê path cụ thể)
   - Thứ tự thực hiện (5-10 step)
   - Test cần viết (unit + integration)
   - Edge case + rủi ro
   - Definition of Done

ĐỪNG CODE. Đợi tôi duyệt plan.
```

#### 📍 Mẫu 4 — Thực thi plan

```
Đọc `docs/plans/003-realtime-chat.md`.

Áp dụng skill `executing-plans` + `test-driven-development`:
1. Làm theo đúng thứ tự trong plan
2. Mỗi step: viết test trước (đỏ) → implement (xanh) → refactor
3. Sau mỗi step, dừng lại báo cáo cho tôi review
4. Nếu phát hiện plan có vấn đề, dừng lại hỏi tôi

Bắt đầu step 1.
```

#### 📍 Mẫu 5 — Debug có hệ thống

```
Bug: [mô tả triệu chứng cụ thể]
Reproduce: [các bước để bug xuất hiện]
Log/Error: [paste full stack trace hoặc đường dẫn file log]

Áp dụng skill `systematic-debugging`:
1. Đọc full stack trace
2. Đưa ra 3 giả thuyết về root cause
3. Với mỗi giả thuyết, kiểm chứng bằng cách đọc code/log/chạy lệnh
4. Sau khi xác định root cause, đề xuất fix
5. CHƯA fix vội — đợi tôi xác nhận giả thuyết đúng

ĐỪNG ĐOÁN. Mọi kết luận phải có evidence.
```

#### 📍 Mẫu 6 — Review code

```
Review tất cả thay đổi chưa commit (`git diff`).

Áp dụng skill `code-review`. Kiểm tra:
- Logic sai, edge case bỏ sót
- Security: SQL injection, XSS, leak secret, missing auth check
- Performance: N+1 query, memory leak, infinite loop
- Vi phạm convention dự án (xem CLAUDE.md)

Bỏ qua nit về formatting, naming style.
Báo theo format: 🔴 Critical / 🟡 Should fix / 🟢 Nice to have.
```

#### 📍 Mẫu 7 — Refactor an toàn

```
File `src/components/Dashboard.tsx` dài 450 dòng, làm 8 việc khác nhau.

Refactor:
1. Tách thành component nhỏ, mỗi component 1 trách nhiệm
2. Tách logic thành custom hooks nếu có thể
3. KHÔNG đổi behavior — UI và API phải giữ nguyên
4. Test hiện tại phải vẫn pass

Sau khi xong, chạy:
- `pnpm test` confirm pass
- `pnpm build` confirm không lỗi
- Mở app local thử các flow chính

Báo cáo kết quả với output thật của các lệnh trên.
```

#### 📍 Mẫu 8 — Verification trước khi báo xong

```
Trước khi nói "Done", áp dụng skill `verification-before-completion`:

1. Liệt kê acceptance criteria của task
2. Với mỗi criteria, chứng minh đã đạt bằng:
   - Output của lệnh test
   - Screenshot UI (nếu là frontend)
   - Curl response (nếu là API)
3. Confirm:
   - Lint pass
   - Type check pass
   - Test cũ vẫn pass
   - Không file rác bị tạo

CHƯA "Done" cho đến khi 100% checklist xanh.
```

### 5.3. Slash commands cốt lõi

| Lệnh | Công dụng |
|---|---|
| `/init` | Tự sinh CLAUDE.md bằng cách phân tích dự án |
| `/plan` (hoặc Shift+Tab) | Plan mode — Claude lập kế hoạch trước khi code |
| `/clear` | Xóa context, bắt đầu chat mới (giữ dự án) |
| `/compact` | Nén context khi gần đầy |
| `/model` | Đổi model (Opus / Sonnet / Haiku) |
| `/review` | Review PR/branch hiện tại |
| `/<skill-name>` | Kích hoạt skill cụ thể |
| `/mcp` | Quản lý MCP servers |
| `/plugin` | Quản lý plugins |
| `/help` | Help |

### 5.4. Phím tắt

| Phím | Hành động |
|---|---|
| **Shift+Tab** | Đổi mode: plan ↔ accept-edits ↔ ask |
| **Esc** | Dừng Claude đang làm |
| **Ctrl+C** 2 lần | Thoát |
| **↑** | Sửa prompt vừa gửi |

### 5.5. Memory — bộ nhớ dài hạn

Claude lưu memory giữa các session để nhớ về bạn và dự án.

**Để Claude nhớ**:
> "Lưu vào memory: tôi prefer dùng `pnpm` thay vì `npm`, đừng đề xuất `npm` nữa."

**Để Claude quên**:
> "Quên cái rule về pnpm đi, project mới này dùng npm."

**Loại memory**:
- `user` — về bạn (vai trò, preference)
- `feedback` — phản hồi về cách AI làm việc
- `project` — về dự án (deadline, ai làm gì)
- `reference` — pointer ngoài (Linear, Slack, Figma...)

---

## 6. Quy Trình Khởi Tạo Dự Án Từ Zero → Hero

> **Mục tiêu**: từ ý tưởng mơ hồ → có dự án skeleton chạy được + spec/plan đầy đủ — trong **1 buổi (3-4h)**.

### Tổng quan 7 bước

```
[1] CHUẨN BỊ      → mkdir, git init, claude
[2] BRAINSTORM    → mô tả ý tưởng, AI hỏi lại
[3] SPEC          → docs/specs/001-product-spec.md
[4] ARCHITECTURE  → docs/plans/001-architecture.md
[5] SKELETON      → tạo cấu trúc thư mục + file rỗng
[6] TASK BREAKDOWN→ chia nhỏ thành 5-10 task
[7] FIRST COMMIT  → git commit khởi đầu
```

### Bước 1 — Chuẩn bị (5 phút)

```bash
mkdir my-awesome-app && cd my-awesome-app
git init
claude
```

### Bước 2 — Brainstorm (30-60 phút)

**Prompt**:
```
Tôi muốn xây dự án sau:
- Mục tiêu: [VD: app quản lý thói quen hàng ngày, web]
- Người dùng: [VD: cá nhân + bạn bè share progress]
- Ngữ cảnh: [VD: dùng trên điện thoại là chính, có notify]
- Sở thích kỹ thuật: [VD: thích Next.js + Postgres, không muốn dùng Firebase]
- Thời gian: [VD: muốn MVP trong 2 tuần]
- Budget: [VD: free tier, deploy Railway]

Áp dụng skill `brainstorming`:
1. Hỏi tôi 8-10 câu để làm rõ
2. Đặc biệt làm rõ: scope MVP, user flow chính, data model sơ bộ
3. ĐỪNG đề xuất gì cho đến khi hỏi đủ
```

→ Trả lời thật chi tiết. Claude càng hỏi → càng tốt.

### Bước 3 — Sinh SPEC (20 phút)

**Prompt**:
```
Dựa vào câu trả lời của tôi, tạo `docs/specs/001-product-spec.md` gồm:

# Product Spec
## 1. Mục tiêu (1-2 câu)
## 2. User personas (2-3 nhân vật)
## 3. User stories (5-10 story dạng: "Là X, tôi muốn Y, để Z")
## 4. User flow chính (vẽ ASCII flowchart)
## 5. Tính năng MVP (must-have)
## 6. Tính năng future (nice-to-have, ngoài MVP)
## 7. Non-goals (cái KHÔNG làm — tránh scope creep)
## 8. Ràng buộc kỹ thuật
## 9. Tiêu chí thành công đo được
## 10. Câu hỏi mở (cái còn chưa rõ)

Sau khi tạo, đọc lại file và CHỈ RA những điểm còn mơ hồ tôi cần quyết.
```

→ Đọc file. Sửa trực tiếp hoặc nhờ Claude sửa: "Phần 5, đổi ý: bỏ tính năng X, thêm Y vì..."

### Bước 4 — Sinh kiến trúc (30 phút)

**Prompt**:
```
Đọc `docs/specs/001-product-spec.md`.

Tạo `docs/plans/001-architecture.md` gồm:

# Architecture
## 1. Tech stack đề xuất (kèm lý do từng lựa chọn)
## 2. Data model (ERD ASCII hoặc bảng)
## 3. API endpoints sơ bộ (REST/GraphQL — list method + path)
## 4. Cấu trúc thư mục (theo template chuẩn)
## 5. Pipeline / data flow (ASCII diagram)
## 6. Trade-off lớn (chọn X thay Y vì... — ít nhất 3 quyết định)
## 7. Rủi ro & cách mitigate
## 8. Plan deploy (local → staging → production)

Trade-off phải thực dụng cho người mới — tránh over-engineering.
```

### Bước 5 — Tạo skeleton (15 phút)

**Prompt**:
```
Đọc `docs/specs/001-product-spec.md` và `docs/plans/001-architecture.md`.

Tạo skeleton dự án:
1. Cấu trúc thư mục đầy đủ
2. File rỗng có docstring/comment mô tả vai trò (không implement logic)
3. `package.json` / `requirements.txt` với dependency cần
4. `CLAUDE.md` (theo template chuẩn)
5. `README.md`: how to run, structure, tech stack
6. `.gitignore` đầy đủ
7. `.env.example` với biến cần (giá trị placeholder)
8. `tests/` với 1 test mẫu (smoke test)
9. Docker setup nếu cần

KHÔNG implement logic thật. Chỉ skeleton + TODO comment.
Mỗi file giải thích 1 dòng nó làm gì khi implement.

Sau khi xong, chạy lệnh setup (npm install / pip install) và confirm chạy được.
```

### Bước 6 — Chia nhỏ task (20 phút)

**Prompt**:
```
Đọc spec + architecture.

Chia MVP thành 5-10 task triển khai độc lập, mỗi task ≤1 ngày làm việc.

Với mỗi task tạo `docs/plans/00X-task-name.md` gồm:
- Mục tiêu task (1 câu)
- Phụ thuộc (task nào phải xong trước)
- Files sẽ tạo/sửa (path cụ thể)
- API/component sẽ tạo
- Test cần viết
- Definition of Done (checklist xanh)
- Ước tính thời gian

Đánh số ưu tiên 001, 002... theo thứ tự nên làm.
Tạo bảng tổng hợp ở `docs/plans/000-roadmap.md` liệt kê tất cả task.
```

### Bước 7 — First commit

```bash
git add .
git commit -m "chore: initial project structure with specs and plans"
git branch -M main
# (tùy chọn) tạo remote và push
gh repo create my-awesome-app --private --source=. --push
```

### 🎉 Sau bước 7 bạn có

✅ Dự án có cấu trúc rõ ràng
✅ Spec mô tả CÁI GÌ phải làm
✅ Architecture mô tả CÁCH triển khai
✅ Roadmap chia thành task nhỏ
✅ Skeleton chạy được local
✅ CLAUDE.md để session sau Claude hiểu dự án ngay

→ Sẵn sàng vào chu kỳ phát triển hàng ngày (mục 7).

---

## 7. Quy Trình Làm Việc Hàng Ngày

### 7.1. Vòng lặp 10 bước cho mỗi task

```
┌────────────────────────────────────────────────────────────┐
│  1. PICK TASK     → Chọn task tiếp theo từ docs/plans/     │
│  2. BRANCH        → git checkout -b feat/task-name         │
│  3. PLAN MODE     → Shift+Tab, Claude review plan, hỏi rõ  │
│  4. TDD           → Viết test trước (test phải FAIL)       │
│  5. IMPLEMENT     → Claude code → test PASS                │
│  6. VERIFY THẬT   → Mở app/API thử bằng tay                │
│  7. REVIEW        → /review hoặc skill code-review         │
│  8. POLISH        → Fix nit, refactor nếu cần              │
│  9. COMMIT        → Conventional commit + PR               │
│ 10. /clear        → Xóa context, sang task tiếp            │
└────────────────────────────────────────────────────────────┘
```

### 7.2. Sample dialogue đầy đủ — task "Add login form"

```
Bạn: Đọc docs/plans/002-implement-auth.md.
     Vào plan mode. Kiểm tra plan có vấn đề gì trước khi code.
     Nêu câu hỏi nếu có chỗ chưa rõ.

Claude: [đọc plan] Plan ổn, nhưng tôi thấy 3 điểm cần xác nhận:
        1. Validation: dùng zod hay yup? (CLAUDE.md không nói)
        2. Token: lưu localStorage hay httpOnly cookie?
        3. Sau login redirect đâu? Plan nói "/dashboard" nhưng route đó chưa tạo

Bạn: 1. zod (đã trong package.json).
     2. httpOnly cookie cho secure.
     3. /dashboard chưa có — tạo placeholder page.

Claude: Rõ. Cập nhật plan.

        Bắt đầu step 1: viết test cho LoginForm component.

        [tạo frontend/tests/LoginForm.test.tsx]
        [chạy pnpm test → 5 fail như mong đợi ✓]

        Step 2: implement LoginForm.
        [tạo frontend/src/components/LoginForm.tsx]
        [chạy pnpm test → 5 pass ✓]

        Step 3: implement /dashboard placeholder + redirect logic.
        [tạo frontend/src/app/dashboard/page.tsx]
        [tạo backend cookie middleware]

        Đã xong implement. Bây giờ verify thật:
        - pnpm test: 47/47 pass ✓
        - pnpm build: success ✓
        - Mở localhost:3000/login, thử login → redirect /dashboard ✓
        - Thử email sai format → hiện error đỏ ✓
        - Thử backend trả 401 → hiện toast "Sai mật khẩu" ✓

        Có muốn tôi screenshot các flow để bạn confirm visual không?

Bạn: Có. Screenshot 3 case: form đẹp, error validation, error backend.

Claude: [dùng MCP playwright/chrome-devtools chụp 3 ảnh]
        [lưu ở docs/screenshots/login-flow/]
        Xong.

Bạn: OK chuẩn. Commit + tạo PR.

Claude: [git add + commit]
        feat(auth): add login form with email validation

        - LoginForm component with zod validation
        - httpOnly cookie token storage
        - /dashboard placeholder with redirect
        - Error handling for 401/422

        [git push + gh pr create]
        PR đã tạo: https://github.com/.../pull/12
```

### 7.3. 3 câu hỏi VÀNG khi không chắc

1. **"Trước khi code, hãy giải thích sẽ làm gì."**
   → Tránh code sai hướng

2. **"Đã verify chưa? Chạy lệnh nào để chứng minh?"**
   → Tránh false success

3. **"Có file/test nào tôi cần review thêm không?"**
   → Tránh sót sót

### 7.4. Khi nào dùng `/clear`

✅ **Nên clear** sau khi:
- Hoàn thành 1 task lớn (đã commit)
- Chuyển sang task không liên quan
- Context thấy "đặc" — Claude bắt đầu chậm/lan man
- Sau khi xong bug debug dài (context đầy log cũ)

❌ **Không nên clear** khi:
- Đang giữa task (mất context plan)
- Vừa thảo luận decision quan trọng chưa lưu vào file

### 7.5. Khi nào dùng git worktree

Khi muốn làm 2 task song song mà không xung đột:

```bash
# Tạo worktree mới
git worktree add ../my-app-feat-x feat/x

# Mở Claude trong worktree đó
cd ../my-app-feat-x && claude
```

→ Mỗi worktree có Claude session riêng, không lẫn lộn.

---

## 8. Ví Dụ Thực Tế Theo Loại Dự Án

### 8.1. 🌐 Web App (Next.js + FastAPI)

**Bước brainstorm — prompt khởi tạo**:
```
Tôi muốn xây web app: chia sẻ recipe nấu ăn cho gia đình.
Stack: Next.js 15 (App Router) + FastAPI + Postgres.
Người dùng: 5-10 thành viên gia đình, share công thức + ảnh.
Auth: Google OAuth.
Hosting: Vercel + Railway.

Brainstorm cùng tôi: hỏi 8 câu để rõ scope MVP.
```

**Đặc thù web app**:
- Setup MCP `chrome-devtools` hoặc `playwright` để Claude tự test UI
- Plugin `frontend-design` cho UI đẹp
- Mỗi feature: nhớ yêu cầu Claude **screenshot** confirm visual
- Test E2E quan trọng — viết Playwright test cho user flow chính

**Cấu trúc**:
```
recipe-share/
├── docs/
├── frontend/                    # Next.js
├── backend/                     # FastAPI
├── infra/
│   ├── docker-compose.yml       # postgres local
│   └── railway.json
├── CLAUDE.md
└── README.md
```

### 8.2. 📱 Mobile App (React Native + Expo)

**Đặc thù**:
- Plugin `figma` để Claude đọc design
- MCP `playwright` không dùng được — yêu cầu user test thật trên emulator
- Kèm screenshot từ user (paste vào chat) để Claude debug UI

**Prompt mẫu khi có design Figma**:
```
Tôi gửi link Figma: figma.com/design/abc123/recipe-app?node-id=1-2

Đọc design qua MCP Figma.
Tạo screen tương ứng trong src/screens/HomeScreen.tsx.
Match pixel-perfect với design.
Dùng styled-components theo theme đã setup ở src/theme/.
```

### 8.3. 🔌 Backend API (FastAPI / Express)

**Đặc thù**:
- Plugin `security-guidance` — quan trọng cho API
- MCP `postgres` để Claude query DB trực tiếp khi debug
- Đặt nặng test integration

**Prompt mẫu cho endpoint mới**:
```
Spec: POST /api/orders — tạo đơn hàng mới.
Yêu cầu: validate input, check stock, tạo Order + OrderItem trong transaction,
publish event "order.created" qua Redis.

Implement theo TDD:
1. Test cases: success / out of stock / invalid input / DB rollback khi event fail
2. Implement endpoint + service + repository
3. Verify bằng curl thật, đính kèm response
```

### 8.4. 🤖 CLI Tool / Automation Script

**Đặc thù**:
- Cấu trúc đơn giản — không cần frontend/backend
- Test bằng cách gọi command thật
- Đầu ra: thường là binary/package publish lên npm/PyPI

**Prompt mẫu**:
```
Xây CLI tool: `myapp init <project-name>` — scaffold dự án mới.

Spec:
- Hỏi user: chọn template (web/api/cli)
- Clone template từ GitHub
- Replace placeholder với tên user nhập
- Cài deps tự động

Implement với commander.js (Node) hoặc click (Python).
Test: chạy lệnh thật trong tmp dir, confirm tạo đúng cấu trúc.
```

### 8.5. 📊 Data Pipeline / ETL

**Đặc thù**:
- Đầu vào lớn — luôn `gitignore data/`
- Cần `notebooks/` cho exploration
- Test với sample data nhỏ

**Prompt mẫu**:
```
Pipeline: đọc CSV bán hàng (10M rows) từ S3, clean, aggregate theo tháng,
xuất Parquet về S3 khác.

Implement với Polars (nhanh hơn Pandas cho data lớn).
Cấu trúc: src/{ingest,transform,export}.

Test với data/sample.csv (1000 rows) — chạy được local trước.
Sau đó test trên S3 thật với bucket dev.
```

### 8.6. 🎮 Game / Real-time App

**Đặc thù**:
- WebSocket / WebRTC phức tạp — đầu tư plan kỹ
- Cần test cùng nhiều client → script automation
- Performance quan trọng → benchmark test

---

## 9. Checklist & Cheatsheet

### 9.1. Checklist khởi tạo dự án mới ✅

- [ ] `git init` xong
- [ ] Cấu trúc thư mục theo template (`docs/`, `src/`, `tests/`)
- [ ] `docs/specs/001-product-spec.md` — đặc tả sản phẩm
- [ ] `docs/plans/001-architecture.md` — kiến trúc
- [ ] `docs/plans/000-roadmap.md` — danh sách task
- [ ] `CLAUDE.md` đầy đủ: tech stack, lệnh, convention, "đừng làm"
- [ ] `README.md` cho người mới
- [ ] `.gitignore` đã loại trừ output/log/secret
- [ ] `.env.example` template (KHÔNG có secret thật)
- [ ] Test framework setup, smoke test pass
- [ ] Plugins đã cài: `superpowers`, `context7`
- [ ] Lệnh chạy local trong README → thử chạy thật → OK
- [ ] First commit "chore: initial structure"

### 9.2. Checklist trước mỗi PR ✅

- [ ] Đọc qua `git diff` — không tin Claude mù quáng
- [ ] Test mới có chạy không? Pass?
- [ ] Test cũ vẫn pass (`pnpm test` / `pytest`)
- [ ] Lint pass (`pnpm lint` / `ruff check`)
- [ ] Type check pass (`tsc --noEmit` / `mypy`)
- [ ] Build pass (`pnpm build`)
- [ ] App chạy local OK (mở browser thử)
- [ ] Không file rác Claude tạo nhầm (`*.md` không yêu cầu)
- [ ] Secret không bị commit (`grep -r "api_key\|password"`)
- [ ] Commit message theo Conventional Commits
- [ ] PR description có screenshot (nếu đổi UI)

### 9.3. Cheatsheet — câu thần chú với Claude

| Tình huống | Câu thần chú |
|---|---|
| Mở dự án mới | "Đọc README và CLAUDE.md, tóm tắt dự án trong 5 dòng" |
| Bắt đầu feature | "Vào plan mode. Brainstorm 3 cách. Tạo plan ở docs/plans/. ĐỪNG CODE." |
| Claude lan man | "Dừng. Chỉ làm đúng việc tôi yêu cầu, không refactor thêm." |
| Bug khó | "Áp dụng systematic-debugging. Đừng đoán, chứng minh giả thuyết." |
| Cần test | "Áp dụng TDD: test trước (đỏ), implement (xanh), refactor." |
| Gần xong | "Áp dụng verification-before-completion. Chứng minh từng acceptance criteria." |
| Review PR | "Dùng skill code-review trên git diff. Format 🔴🟡🟢." |
| Design Figma | "Đọc figma.com/design/X qua MCP, tạo component match pixel." |
| API mới | "Implement TDD. Test integration với DB thật, không mock." |
| Refactor | "KHÔNG đổi behavior. Test cũ phải pass. Chứng minh bằng output." |
| Hết context | "/compact" hoặc "/clear" |

### 9.4. Cheatsheet — Anti-patterns TRÁNH

| Đừng làm | Tại sao | Thay bằng |
|---|---|---|
| ❌ "Làm cái app gì hay hay" | Quá mơ hồ, AI tự bịa | Mô tả rõ user, mục tiêu, ràng buộc |
| ❌ Để Claude code không plan | Khó review, dễ over-engineer | Plan mode → spec → plan → code |
| ❌ Tin "Done!" mà không verify | False success rất thường xuyên | Yêu cầu output lệnh + screenshot |
| ❌ Dồn 5 task vào 1 session | Context loãng, chất lượng giảm | 1 session = 1 task |
| ❌ Commit `output/`, `node_modules/` | Repo nặng, conflict | `.gitignore` đầy đủ ngay từ đầu |
| ❌ Skip test "cho nhanh" | Nợ kỹ thuật tích lũy | TDD luôn, kể cả prototype |
| ❌ Sửa file mà chưa đọc | Phá logic ngầm | Yêu cầu Claude đọc file trước |
| ❌ Hardcode secret trong code | Security risk | `.env` + `.env.example` |
| ❌ Bỏ qua warning lint | Sau này sửa rất tốn | Fix ngay khi xuất hiện |
| ❌ Force push lên main | Mất code | Luôn PR, review trước merge |

---

## 10. Xử Lý Tình Huống Thường Gặp

### 10.1. "Claude code lung tung, không theo plan"

**Triệu chứng**: yêu cầu sửa 1 chỗ, Claude refactor 5 file khác.

**Fix**:
```
Dừng. Revert tất cả thay đổi (git checkout -- .).
Chỉ làm đúng việc tôi yêu cầu: [task cụ thể].
KHÔNG sửa file ngoài [danh sách file].
KHÔNG refactor. KHÔNG cải thiện code khác.
```

### 10.2. "Claude tạo file mà tôi không yêu cầu"

**Triệu chứng**: tự tạo `IMPLEMENTATION_NOTES.md`, `SUMMARY.md`...

**Fix**: thêm vào `CLAUDE.md`:
```markdown
## Đừng làm
- KHÔNG tạo file *.md mới trừ khi tôi yêu cầu
- KHÔNG tạo file README/SUMMARY/NOTES sau task
```

### 10.3. "Test pass nhưng feature thực tế lỗi"

**Triệu chứng**: Claude báo "Done, all tests pass" nhưng mở app vẫn lỗi.

**Fix**:
- Test có thể quá generic, không cover case thật
- **Luôn verify thủ công** sau khi test pass:
  ```
  Mở app local, thử [user flow X]. Quay video/screenshot bước thực hiện.
  ```

### 10.4. "Hết context giữa task"

**Triệu chứng**: Claude bắt đầu quên việc đã làm, lặp lại.

**Fix**:
1. **Dừng ngay**, đừng để Claude làm tiếp
2. Yêu cầu Claude lưu trạng thái:
   ```
   Tóm tắt vào docs/plans/current-task-state.md:
   - Đã làm gì (với commit hash nếu có)
   - Đang làm dở chỗ nào
   - Bước tiếp theo cụ thể
   ```
3. `/clear`
4. Session mới: "Đọc docs/plans/current-task-state.md, tiếp tục từ chỗ dừng"

### 10.5. "Claude đề xuất giải pháp lỗi thời"

**Triệu chứng**: dùng API cũ, syntax cũ của library.

**Fix**: cài plugin **`context7`** — Claude tự tra docs mới nhất.

Hoặc prompt:
```
Trước khi code, dùng context7 tra docs mới nhất của [library].
KHÔNG dựa vào training data — code phải khớp version đang dùng.
```

### 10.6. "Quá nhiều quyết định cần làm"

**Triệu chứng**: Claude hỏi 20 câu cùng lúc, bạn quyết không xuể.

**Fix**:
```
Hỏi từng câu 1. Sau mỗi câu trả lời, đặt câu tiếp theo.
Đặt câu hỏi quan trọng nhất trước.
Nếu có default hợp lý, đề xuất luôn để tôi confirm/đổi.
```

### 10.7. "Bug khó, Claude đoán mãi không trúng"

**Fix nghiêm túc**:
```
Dừng đoán. Áp dụng systematic-debugging:

1. Đọc full stack trace (paste lại đây)
2. Đọc code dòng gây lỗi (file:line)
3. Kiểm tra git log: lỗi xuất hiện từ commit nào?
4. Đưa 3 giả thuyết với evidence cụ thể
5. Với mỗi giả thuyết, xác định cách chứng minh đúng/sai
6. Thực hiện kiểm chứng trước khi đề xuất fix

Không đoán. Không thử random. Mọi bước phải có lý do.
```

### 10.8. "Không biết Claude làm gì trong code"

**Fix**: yêu cầu giải thích trước khi áp dụng:
```
Trước khi sửa, giải thích:
1. File nào sẽ thay đổi
2. Logic mới hoạt động ra sao (pseudocode)
3. Tại sao chọn cách này thay vì cách khác

Đợi tôi confirm rồi mới code.
```

### 10.9. "Dự án nhiều người, conflict liên tục"

**Fix**:
- Mỗi feature → 1 branch + 1 worktree riêng
- Mỗi branch → 1 task trong `docs/plans/`
- Luôn `git pull origin main` trước khi bắt đầu
- Skill `using-git-worktrees` để Claude tự cô lập

### 10.10. "Claude vi phạm convention dự án"

**Triệu chứng**: dùng `var` thay `const`, `default export` thay `named export`...

**Fix**: `CLAUDE.md` phải nêu rõ convention. Ngoài ra:
```
Đọc CLAUDE.md mục "Quy ước code".
Review code vừa viết, chỉ ra chỗ vi phạm convention, sửa lại.
```

---

## 🎯 Tổng Kết — Một Câu

> **"Cấu trúc thư mục rõ + Spec/Plan trước khi code + Prompt cụ thể + Verify trước khi xong = Claude trở thành lập trình viên đáng tin trong team."**

### 5 thói quen vàng

1. 📖 **Mọi tính năng bắt đầu từ `docs/specs/` và `docs/plans/`**, không bao giờ code thẳng
2. 🤖 **`CLAUDE.md` là tài sản** — đầu tư viết kỹ, cập nhật thường xuyên
3. 🔍 **"Show me, don't tell me"** — yêu cầu output thật, không tin lời báo cáo
4. 🧪 **TDD luôn** — test trước, code sau, verify cuối
5. 💾 **1 session = 1 task** — `/clear` thường xuyên, đừng tham

---

## 📎 Phụ Lục

### A. Lệnh git thường dùng

```bash
git status                      # Trạng thái
git diff                        # Thay đổi chưa stage
git diff --staged               # Đã stage
git log --oneline -10           # 10 commit gần nhất
git checkout -b feat/X          # Branch mới
git worktree add ../app-X feat/X # Worktree song song
gh pr create                    # PR (cần gh CLI)
gh pr view --web                # Mở PR trong browser
```

### B. Conventional Commits

```
<type>(<scope>): <subject>

Type:
- feat:     tính năng mới
- fix:      sửa bug
- docs:     tài liệu
- style:    format (không đổi logic)
- refactor: refactor (không thêm feature/sửa bug)
- test:     thêm/sửa test
- chore:    cập nhật build/deps
- perf:     cải thiện hiệu năng
- ci:       sửa CI/CD
```

Ví dụ:
```
feat(auth): add Google OAuth login

- Add NextAuth provider config
- Create login/callback routes
- Persist user to database on first login

Closes #42
```

### C. Lệnh test phổ biến

| Stack | Test | Lint | Type check | Build |
|---|---|---|---|---|
| Node + TS | `pnpm test` | `pnpm lint` | `tsc --noEmit` | `pnpm build` |
| Python | `pytest -xvs` | `ruff check .` | `mypy .` | (không có) |
| Go | `go test ./...` | `golangci-lint` | (built-in) | `go build` |
| Rust | `cargo test` | `cargo clippy` | (built-in) | `cargo build --release` |

### D. Liên kết hữu ích

- Claude Code docs: https://docs.claude.com/claude-code
- Plugin marketplace: lệnh `/plugin` trong Claude Code
- MCP servers: https://github.com/modelcontextprotocol/servers
- Conventional Commits: https://www.conventionalcommits.org
- 12 Factor App: https://12factor.net (best practices web app)
- Semantic Versioning: https://semver.org

### E. Template files

Khi cần template nhanh, prompt Claude:
```
Tạo file [tên file] theo best practice cho [stack].
Bao gồm các phần phổ biến nhất.
```

Ví dụ:
- `.gitignore` cho Node + Python
- `Dockerfile` multi-stage cho Next.js
- `docker-compose.yml` cho dev với Postgres + Redis
- `.github/workflows/ci.yml` cho test + deploy
- `README.md` template

---

*Tài liệu sống — cập nhật khi quy trình team thay đổi.*
*Phiên bản: 2.0 — 2026-05-01*
