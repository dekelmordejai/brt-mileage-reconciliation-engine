"""Administración local. Nunca crea usuarios o datos por defecto al iniciar el servidor."""

import argparse
import getpass
import json
from pathlib import Path

from .main import import_source
from .security import password_hash
from .store import Store


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    user = sub.add_parser("user")
    user.add_argument("username")
    user.add_argument("--role", choices=["admin", "analyst", "reviewer", "viewer"], default="admin")
    imp = sub.add_parser("import")
    imp.add_argument("kind")
    imp.add_argument("path")
    imp.add_argument("--sheet")
    sub.add_parser("demo")
    args = parser.parse_args()
    store = Store()
    with store.connect() as db:
        if args.command == "user":
            password = getpass.getpass("Contraseña (mínimo 12 caracteres): ")
            if password != getpass.getpass("Repetir contraseña: "):
                raise SystemExit("Las contraseñas no coinciden")
            db.execute(
                "INSERT INTO users(id,password,role) VALUES(?,?,?)",
                (args.username, password_hash(password), args.role),
            )
            store.audit(db, "local-admin", "USER_CREATED", {"id": args.username, "role": args.role})
            print("Usuario creado")
        elif args.command == "import":
            p = Path(args.path)
            print(
                json.dumps(
                    import_source(
                        store, db, args.kind, p.name, p.read_bytes(), "local-admin", args.sheet
                    ),
                    ensure_ascii=False,
                )
            )
        else:
            if (
                db.execute("SELECT 1 FROM sources LIMIT 1").fetchone()
                or db.execute("SELECT 1 FROM users LIMIT 1").fetchone()
            ):
                raise SystemExit("La demo requiere una base vacía para no mezclar datos")
            for name, role in [
                ("demo-admin", "admin"),
                ("demo-analista", "analyst"),
                ("demo-revisor", "reviewer"),
            ]:
                db.execute(
                    "INSERT INTO users(id,password,role) VALUES(?,?,?)",
                    (name, password_hash("Demo-local-2026!"), role),
                )
            fixture = Path(__file__).resolve().parent / "demo.json"
            for kind, rows in json.loads(fixture.read_text(encoding="utf-8")).items():
                import_source(
                    store, db, kind, kind + ".json", json.dumps(rows).encode(), "demo-admin"
                )
            store.audit(db, "local-admin", "DEMO_INITIALIZED", {})
            print(
                "Demo sintética: demo-admin / demo-analista / demo-revisor. Contraseña: Demo-local-2026!"
            )


if __name__ == "__main__":
    main()
