"""Create local development-only credentials once; never print their values."""

import os
import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / ".env"
if path.exists():
    print("Existing .env preserved")
else:
    password = secrets.token_hex(24)
    secret = secrets.token_hex(32)
    with os.fdopen(
        os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w"
    ) as f:
        f.write(
            f"POSTGRES_PASSWORD={password}\nATLAS_DATABASE_URL=postgresql+psycopg://atlasops:{password}@127.0.0.1:5432/atlasops\n"
        )
        f.write(
            f"ATLAS_MODE=development\nATLAS_DEV_AUTH_ENABLED=true\nATLAS_DEV_AUTH_SECRET={secret}\n"
        )
        f.write(
            "ATLAS_REDIS_URL=redis://127.0.0.1:6379/0\nATLAS_REPORT_TIMEZONE=Asia/Kolkata\n"
        )
        f.write(
            "ATLAS_INTEGRATION_HOSTS=127.0.0.1,localhost,prometheus,grafana\nATLAS_ALLOW_INSECURE_INTEGRATIONS=true\n"
        )
    print("Created private .env for local development. Do not commit it.")
