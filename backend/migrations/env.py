from alembic import context
from app.db import engine
from app.models import Base

if context.is_offline_mode():
    context.configure(url="postgresql+psycopg://", target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    from contextlib import nullcontext

    supplied = context.config.attributes.get("connection")
    with nullcontext(supplied) if supplied is not None else engine().connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
