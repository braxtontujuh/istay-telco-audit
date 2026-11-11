from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import (
    Block,
    Floor,
    Location,
    RoomTemplate,
    RoomTemplateItem,
    Site,
    Telco,
    Unit,
    User,
    UserSiteAccess,
)
from app.security import (
    allowed_sites,
    current_user,
    hasher,
    mutation,
    require_role,
    require_site,
    revoke_sessions,
)
from app.workflow_contracts import (
    ApplyTemplate,
    BlockInput,
    FloorInput,
    LocationInput,
    Named,
    SiteInput,
    TemplateInput,
    UnitImport,
    UnitInput,
    UnitPatch,
    UserCreate,
    UserPatch,
)

router = APIRouter(prefix="/api/v1", tags=["Configuration"])


def get_or_404(db, model, id):
    value = db.get(model, id)
    if value is None:
        raise HTTPException(404, "NOT_FOUND")
    return value


def row(value, *fields):
    return {key: getattr(value, key) for key in ("id", *fields)}


def manager(user):
    require_role(user, "ADMIN", "MANAGER")


def site_for_unit(db, unit_id):
    unit = get_or_404(db, Unit, unit_id)
    floor = get_or_404(db, Floor, unit.floor_id)
    block = get_or_404(db, Block, floor.block_id)
    return block.site_id


def location_context(db, location_id):
    location = get_or_404(db, Location, location_id)
    unit = get_or_404(db, Unit, location.unit_id)
    floor = get_or_404(db, Floor, unit.floor_id)
    block = get_or_404(db, Block, floor.block_id)
    site = get_or_404(db, Site, block.site_id)
    return location, unit, floor, block, site


def location_row(value):
    return row(value, "unit_id", "code", "name", "sort_order", "active")


@router.post("/sites", status_code=201)
def create_site(payload: SiteInput, user: User = Depends(mutation), db: Session = Depends(get_db)):
    require_role(user, "ADMIN")
    value = Site(**payload.model_dump())
    db.add(value)
    db.commit()
    return row(value, "code", "name", "active")


@router.patch("/sites/{site_id}")
def update_site(
    site_id: int, payload: SiteInput, user: User = Depends(mutation), db: Session = Depends(get_db)
):
    require_role(user, "ADMIN")
    value = get_or_404(db, Site, site_id)
    for key, item in payload.model_dump().items():
        setattr(value, key, item)
    db.commit()
    return row(value, "code", "name", "active")


@router.get("/sites/{site_id}/blocks")
def blocks(site_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    manager(user)
    require_site(db, user, site_id)
    return [
        row(item, "site_id", "code")
        for item in db.scalars(select(Block).where(Block.site_id == site_id).order_by(Block.code))
    ]


@router.post("/blocks", status_code=201)
def create_block(payload: BlockInput, user: User = Depends(mutation), db: Session = Depends(get_db)):
    require_role(user, "ADMIN")
    require_site(db, user, payload.site_id)
    value = Block(**payload.model_dump())
    db.add(value)
    db.commit()
    return row(value, "site_id", "code")


@router.get("/blocks/{block_id}/floors")
def floors(block_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    manager(user)
    require_site(db, user, get_or_404(db, Block, block_id).site_id)
    return [
        row(item, "block_id", "floor_no")
        for item in db.scalars(select(Floor).where(Floor.block_id == block_id).order_by(Floor.floor_no))
    ]


@router.post("/floors", status_code=201)
def create_floor(payload: FloorInput, user: User = Depends(mutation), db: Session = Depends(get_db)):
    require_role(user, "ADMIN")
    require_site(db, user, get_or_404(db, Block, payload.block_id).site_id)
    value = Floor(**payload.model_dump())
    db.add(value)
    db.commit()
    return row(value, "block_id", "floor_no")


@router.get("/floors/{floor_id}/units")
def units(floor_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    manager(user)
    floor = get_or_404(db, Floor, floor_id)
    require_site(db, user, get_or_404(db, Block, floor.block_id).site_id)
    return [
        row(item, "floor_id", "unit_no", "active")
        for item in db.scalars(select(Unit).where(Unit.floor_id == floor_id).order_by(Unit.unit_no))
    ]


def add_unit(db, payload):
    value = Unit(floor_id=payload.floor_id, unit_no=payload.unit_no)
    db.add(value)
    db.flush()
    for item in payload.locations:
        db.add(Location(unit_id=value.id, **item.model_dump()))
    return value


@router.post("/units", status_code=201)
def create_unit(payload: UnitInput, user: User = Depends(mutation), db: Session = Depends(get_db)):
    require_role(user, "ADMIN")
    floor = get_or_404(db, Floor, payload.floor_id)
    require_site(db, user, get_or_404(db, Block, floor.block_id).site_id)
    value = add_unit(db, payload)
    db.commit()
    return row(value, "floor_id", "unit_no", "active")


@router.post("/units/import", status_code=201)
def import_units(payload: UnitImport, user: User = Depends(mutation), db: Session = Depends(get_db)):
    require_role(user, "ADMIN")
    values = []
    for item in payload.units:
        floor = get_or_404(db, Floor, item.floor_id)
        require_site(db, user, get_or_404(db, Block, floor.block_id).site_id)
        values.append(add_unit(db, item))
    db.commit()
    return [row(value, "floor_id", "unit_no", "active") for value in values]


@router.patch("/units/{unit_id}")
def update_unit(
    unit_id: int, payload: UnitPatch, user: User = Depends(mutation), db: Session = Depends(get_db)
):
    require_role(user, "ADMIN")
    require_site(db, user, site_for_unit(db, unit_id))
    value = get_or_404(db, Unit, unit_id)
    for key, item in payload.model_dump(exclude_unset=True).items():
        if item is None:
            raise HTTPException(422, "NULL_NOT_ALLOWED")
        setattr(value, key, item)
    db.commit()
    return row(value, "floor_id", "unit_no", "active")


@router.get("/units/{unit_id}/locations")
def locations(unit_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    manager(user)
    require_site(db, user, site_for_unit(db, unit_id))
    return [
        location_row(item)
        for item in db.scalars(
            select(Location).where(Location.unit_id == unit_id).order_by(Location.sort_order, Location.id)
        )
    ]


@router.post("/units/{unit_id}/locations", status_code=201)
def create_location(
    unit_id: int, payload: LocationInput, user: User = Depends(mutation), db: Session = Depends(get_db)
):
    require_role(user, "ADMIN")
    require_site(db, user, site_for_unit(db, unit_id))
    value = Location(unit_id=unit_id, **payload.model_dump())
    db.add(value)
    db.commit()
    return location_row(value)


@router.patch("/locations/{location_id}")
def update_location(
    location_id: int, payload: LocationInput, user: User = Depends(mutation), db: Session = Depends(get_db)
):
    require_role(user, "ADMIN")
    value = get_or_404(db, Location, location_id)
    require_site(db, user, site_for_unit(db, value.unit_id))
    for key, item in payload.model_dump().items():
        setattr(value, key, item)
    db.commit()
    return location_row(value)


@router.get("/telcos")
def telcos(user: User = Depends(current_user), db: Session = Depends(get_db)):
    query = select(Telco).order_by(Telco.name)
    if user.role != "ADMIN":
        query = query.where(Telco.active.is_(True))
    return [row(item, "name", "active") for item in db.scalars(query)]


@router.post("/telcos", status_code=201)
def create_telco(payload: Named, user: User = Depends(mutation), db: Session = Depends(get_db)):
    require_role(user, "ADMIN")
    value = Telco(**payload.model_dump())
    db.add(value)
    db.commit()
    return row(value, "name", "active")


@router.patch("/telcos/{telco_id}")
def update_telco(
    telco_id: int, payload: Named, user: User = Depends(mutation), db: Session = Depends(get_db)
):
    require_role(user, "ADMIN")
    value = get_or_404(db, Telco, telco_id)
    value.name, value.active = payload.name, payload.active
    db.commit()
    return row(value, "name", "active")


def template_view(db, value):
    return row(value, "name") | {
        "items": [
            row(item, "code", "name", "sort_order")
            for item in db.scalars(
                select(RoomTemplateItem)
                .where(RoomTemplateItem.template_id == value.id)
                .order_by(RoomTemplateItem.sort_order, RoomTemplateItem.id)
            )
        ]
    }


@router.get("/room-templates")
def templates(user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_role(user, "ADMIN")
    return [template_view(db, item) for item in db.scalars(select(RoomTemplate).order_by(RoomTemplate.name))]


def replace_template_items(db, value, payload):
    value.name = payload.name
    db.flush()
    db.execute(delete(RoomTemplateItem).where(RoomTemplateItem.template_id == value.id))
    for item in payload.items:
        db.add(RoomTemplateItem(template_id=value.id, **item.model_dump(exclude={"active"})))


@router.post("/room-templates", status_code=201)
def create_template(payload: TemplateInput, user: User = Depends(mutation), db: Session = Depends(get_db)):
    require_role(user, "ADMIN")
    value = RoomTemplate(name=payload.name)
    db.add(value)
    replace_template_items(db, value, payload)
    db.commit()
    return template_view(db, value)


@router.patch("/room-templates/{template_id}")
def update_template(
    template_id: int, payload: TemplateInput, user: User = Depends(mutation), db: Session = Depends(get_db)
):
    require_role(user, "ADMIN")
    value = get_or_404(db, RoomTemplate, template_id)
    replace_template_items(db, value, payload)
    db.commit()
    return template_view(db, value)


@router.delete("/room-templates/{template_id}", status_code=204)
def delete_template(template_id: int, user: User = Depends(mutation), db: Session = Depends(get_db)):
    require_role(user, "ADMIN")
    value = get_or_404(db, RoomTemplate, template_id)
    db.execute(delete(RoomTemplateItem).where(RoomTemplateItem.template_id == value.id))
    db.delete(value)
    db.commit()


@router.post("/room-templates/{template_id}/apply")
def apply_template(
    template_id: int, payload: ApplyTemplate, user: User = Depends(mutation), db: Session = Depends(get_db)
):
    require_role(user, "ADMIN")
    get_or_404(db, RoomTemplate, template_id)
    items = list(db.scalars(select(RoomTemplateItem).where(RoomTemplateItem.template_id == template_id)))
    for unit_id in sorted(set(payload.unit_ids)):
        require_site(db, user, site_for_unit(db, unit_id))
        db.scalar(select(Unit).where(Unit.id == unit_id).with_for_update())
        current = {
            value.code: value for value in db.scalars(select(Location).where(Location.unit_id == unit_id))
        }
        for value in current.values():
            value.active = False
        for item in items:
            value = current.get(item.code)
            if value is None:
                value = Location(unit_id=unit_id, code=item.code, name=item.name)
                db.add(value)
            value.name, value.sort_order, value.active = item.name, item.sort_order, True
    db.commit()
    return {"updated_units": len(set(payload.unit_ids))}


def validate_site_ids(db, site_ids):
    ids = set(site_ids)
    existing = set(db.scalars(select(Site.id).where(Site.id.in_(ids), Site.active.is_(True))))
    if ids != existing:
        raise HTTPException(422, "INVALID_SITE_IDS")


def user_view(db, value):
    return row(value, "username", "full_name", "role", "active") | {
        "site_ids": list(db.scalars(select(UserSiteAccess.site_id).where(UserSiteAccess.user_id == value.id)))
    }


@router.get("/users")
def users(user: User = Depends(current_user), db: Session = Depends(get_db)):
    manager(user)
    values = list(db.scalars(select(User).order_by(User.full_name)))
    if user.role == "MANAGER":
        permitted = set(allowed_sites(db, user))
        values = [
            item
            for item in values
            if item.active and item.role != "ADMIN" and set(allowed_sites(db, item)) & permitted
        ]
    result = [user_view(db, value) for value in values]
    if user.role == "MANAGER":
        for value in result:
            value["site_ids"] = sorted(set(value["site_ids"]) & permitted)
    return result


@router.post("/users", status_code=201)
def create_user(payload: UserCreate, user: User = Depends(mutation), db: Session = Depends(get_db)):
    require_role(user, "ADMIN")
    validate_site_ids(db, payload.site_ids)
    value = User(
        username=payload.username,
        full_name=payload.full_name,
        role=payload.role,
        password_hash=hasher.hash(payload.password),
    )
    db.add(value)
    db.flush()
    for site_id in set(payload.site_ids):
        db.add(UserSiteAccess(user_id=value.id, site_id=site_id))
    db.commit()
    return user_view(db, value)


@router.patch("/users/{user_id}")
def update_user(
    user_id: int, payload: UserPatch, user: User = Depends(mutation), db: Session = Depends(get_db)
):
    require_role(user, "ADMIN")
    value = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if value is None:
        raise HTTPException(404, "NOT_FOUND")
    if user_id == user.id and ((payload.role and payload.role != "ADMIN") or payload.active is False):
        raise HTTPException(409, "CANNOT_DISABLE_OWN_ADMIN_ACCOUNT")
    changes = payload.model_dump(exclude_unset=True)
    if any(item is None for item in changes.values()):
        raise HTTPException(422, "NULL_NOT_ALLOWED")
    if payload.site_ids is not None:
        validate_site_ids(db, payload.site_ids)
        db.execute(delete(UserSiteAccess).where(UserSiteAccess.user_id == user_id))
        for site_id in set(payload.site_ids):
            db.add(UserSiteAccess(user_id=user_id, site_id=site_id))
    for key in ("full_name", "role", "active"):
        if key in changes:
            setattr(value, key, changes[key])
    if any(key in changes for key in ("role", "active", "site_ids")):
        revoke_sessions(db, user_id)
    db.commit()
    return user_view(db, value)
