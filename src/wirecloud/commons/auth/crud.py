# -*- coding: utf-8 -*-
# Copyright (c) 2026 Future Internet Consulting and Development Solutions S.L.

# This file is part of Wirecloud.

# Wirecloud is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# Wirecloud is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.

# You should have received a copy of the GNU Affero General Public License
# along with Wirecloud.  If not, see <http://www.gnu.org/licenses/>.

from typing import Optional
from datetime import datetime, timezone

from bson import ObjectId

from wirecloud.commons.auth.schemas import User, UserWithPassword, Permission, UserAll, UserCreate, GroupCreate, \
    OrganizationCreate
from wirecloud.commons.auth.models import DBUser as UserModel
from wirecloud.commons.auth.models import DBLoginAttempt
from wirecloud.commons.auth.models import Group as GroupModel, Group
from wirecloud.commons.auth.models import DBPlatformPreference as PlatformPreferenceModel
from wirecloud.database import DBSession, Id


async def ensure_login_attempt_indexes(db: DBSession) -> None:
    await db.client.login_attempts.create_index("expires_at", expireAfterSeconds=0)


async def create_login_attempt(db: DBSession, attempt: DBLoginAttempt) -> None:
    await db.client.login_attempts.insert_one(attempt.model_dump(by_alias=True))


async def consume_login_attempt(
    db: DBSession, attempt_id: str, browser: str, current_time: datetime
) -> Optional[DBLoginAttempt]:
    attempt = await db.client.login_attempts.find_one_and_delete(
        {"_id": attempt_id, "browser": browser, "expires_at": {"$gt": current_time}}
    )
    return DBLoginAttempt.model_validate(attempt) if attempt is not None else None


async def create_token(db: DBSession, expiration: datetime, user_id: Id, idm_session: Optional[str] = None) -> ObjectId:
    token = {
        "_id": ObjectId(),
        "valid": True,
        "expiration": expiration,
        "user_id": user_id
    }

    if idm_session is not None:
        token["idm_session"] = idm_session

    await db.client.tokens.insert_one(token)
    return token["_id"]


async def is_token_valid(db: DBSession, token_id: ObjectId) -> bool:
    token = await db.client.tokens.find_one({"_id": token_id})

    if token is None:
        return False

    exp_datetime = token.get("expiration")
    exp_datetime = exp_datetime.replace(tzinfo=timezone.utc)  # Ensure the expiration datetime is timezone-aware
    if exp_datetime < datetime.now(timezone.utc):
        return False

    return token["valid"]


async def set_token_expiration(db: DBSession, token_id: ObjectId, expiration: datetime) -> None:
    query = {"_id": token_id}, {"$set": {"expiration": expiration}}
    await db.client.tokens.update_one(*query)


async def get_token_expiration(db: DBSession, token_id: ObjectId) -> Optional[datetime]:
    token = await db.client.tokens.find_one({"_id": token_id})
    return token["expiration"] if token is not None else None


async def invalidate_token(db: DBSession, token_id: ObjectId) -> None:
    query = {"_id": token_id}, {"$set": {"valid": False}}
    await db.client.tokens.update_one(*query)


async def invalidate_tokens_by_idm_session(db: DBSession, idm_session: str) -> None:
    query = {"idm_session": idm_session}, {"$set": {"valid": False}}
    await db.client.tokens.update_many(*query)


async def invalidate_all_user_tokens(db: DBSession, user_id: Id) -> None:
    query = {"user_id": user_id}, {"$set": {"valid": False}}
    await db.client.tokens.update_many(*query)


async def get_token_idm_session(db: DBSession, token_id: ObjectId) -> Optional[str]:
    token = await db.client.tokens.find_one({"_id": token_id})
    return token.get("idm_session")


async def create_user_db(db: DBSession, user_info: UserCreate) -> UserModel:
    default_permissions = ["WORKSPACE.CREATE", "COMPONENT.INSTALL", "COMPONENT.UNINSTALL", "MARKETPLACE.CREATE"]
    user_created = UserModel(
        _id=ObjectId(),
        username=user_info.username,
        password=user_info.password,
        first_name=user_info.first_name,
        last_name=user_info.last_name,
        email=user_info.email,
        is_superuser=user_info.is_superuser,
        is_staff=user_info.is_staff,
        is_active=user_info.is_active,
        idm_data=user_info.idm_data,
        date_joined=datetime.now(timezone.utc),
        last_login=None,
        user_permissions=[Permission(codename=perm) for perm in default_permissions]
    )

    await db.client.users.insert_one(user_created.model_dump(by_alias=True))
    return user_created


async def update_user(db: DBSession, user_info: User) -> None:
    # Make sure the user_info is a User and not UserAll or similar
    from wirecloud.commons.search import add_user_to_index
    user_info = User(**user_info.model_dump(include=User.model_fields.keys()))

    query = {"_id": ObjectId(user_info.id)}, {"$set": user_info.model_dump(by_alias=True, exclude={"id"})}
    await db.client.users.update_one(*query)
    await add_user_to_index(user_info)


async def update_user_with_all_info(db: DBSession, user: UserAll) -> None:
    from wirecloud.commons.search import add_user_to_index
    query = {"_id": ObjectId(user.id)}

    data = user.model_dump(exclude={"id"}, by_alias=True)
    await db.client.users.update_one(query, {"$set": data})
    await add_user_to_index(user)


async def delete_user(db: DBSession, user: User) -> None:
    from wirecloud.commons.search import delete_user_from_index
    await invalidate_all_user_tokens(db, user.id)
    await remove_user_from_all_groups(db, user.id)

    query = {"_id": ObjectId(user.id)}

    await db.client.users.delete_one(query)
    await delete_user_from_index(user)


async def get_user_by_id(db: DBSession, user_id: Id) -> Optional[User]:
    query = {"_id": ObjectId(user_id)}
    user_data = await db.client.users.find_one(query)

    if user_data is None:
        return None

    user = UserModel.model_validate(user_data)

    return User(
        id=user.id,
        username=user.username,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        is_superuser=user.is_superuser,
        is_staff=user.is_staff,
        is_active=user.is_active,
        date_joined=user.date_joined,
        last_login=user.last_login,
        idm_data=user.idm_data
    )


async def get_all_user_permissions(db: DBSession, user_id: Id) -> list[Permission]:
    permission_codenames = set()

    individual_permissions_query = {"_id": ObjectId(user_id)}
    individual_permissions = await db.client.users.find_one(individual_permissions_query)

    if individual_permissions is None:
        return []

    for permission in individual_permissions.get("user_permissions"):
        permission_codenames.add(permission.get("codename"))

    group_ids = individual_permissions.get("groups")
    for permission in individual_permissions.get("user_permissions"):
        permission_codenames.add(permission.get("codename"))

    group_permissions_query = {"_id": {"$in": group_ids}}
    group_permissions = await db.client.groups.find(group_permissions_query).to_list()
    for group in group_permissions:
        for permission in group.get("group_permissions"):
            permission_codenames.add(permission.get("codename"))

    return [Permission(codename=codename) for codename in permission_codenames]


async def get_user_with_all_info(db: DBSession, user_id: Id, only_user_permissions: bool = False) -> Optional[UserAll]:
    query = {"_id": ObjectId(user_id)}
    user_data = await db.client.users.find_one(query)

    if user_data is None:
        return None

    user = UserModel.model_validate(user_data)
    return UserAll(
        id=user.id,
        username=user.username,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        is_superuser=user.is_superuser,
        is_staff=user.is_staff,
        is_active=user.is_active,
        date_joined=user.date_joined,
        last_login=user.last_login,
        idm_data=user.idm_data,
        groups=user.groups,
        permissions=user.user_permissions if only_user_permissions else await get_all_user_permissions(db, user.id)
    )


async def get_user_with_all_info_by_username(db: DBSession, username: str, only_user_permissions: bool = False) -> Optional[UserAll]:
    query = {"username": username}
    user_data = await db.client.users.find_one(query)

    if user_data is None:
        return None

    user = UserModel.model_validate(user_data)
    return UserAll(
        id=user.id,
        username=user.username,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        is_superuser=user.is_superuser,
        is_staff=user.is_staff,
        is_active=user.is_active,
        date_joined=user.date_joined,
        last_login=user.last_login,
        idm_data=user.idm_data,
        groups=user.groups,
        permissions=user.user_permissions if only_user_permissions else await get_all_user_permissions(db, user.id)
    )


async def get_user_by_username(db: DBSession, username: str) -> Optional[User]:
    query = {"username": username}
    user = await db.client.users.find_one(query)

    if user is None:
        return None

    user = UserModel.model_validate(user)

    return User(
        id=user.id,
        username=user.username,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        is_superuser=user.is_superuser,
        is_staff=user.is_staff,
        is_active=user.is_active,
        date_joined=user.date_joined,
        last_login=user.last_login,
        idm_data=user.idm_data
    )


async def get_user_groups(db: DBSession, user_id: Id) -> list[Group]:
    query = {"users": user_id}
    results = [GroupModel.model_validate(result) for result in await db.client.groups.find(query).to_list()]
    return results


async def get_user_with_password(db: DBSession, username: str) -> Optional[UserWithPassword]:
    query = {"username": username}
    user = await db.client.users.find_one(query)

    if user is None:
        return None

    user = UserModel.model_validate(user)

    return UserWithPassword(
        id=user.id,
        username=user.username,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        is_superuser=user.is_superuser,
        is_staff=user.is_staff,
        is_active=user.is_active,
        date_joined=user.date_joined,
        last_login=user.last_login,
        idm_data=user.idm_data,
        password=user.password
    )


async def add_user_to_groups_by_codename(db: DBSession, user_id: Id, group_names: list[str]) -> None:
    query = {"codename": {"$in": group_names}}
    groups = await db.client.groups.find(query).to_list()

    user_query = {"_id": ObjectId(user_id)}
    user = await db.client.users.find_one(user_query, {"groups": 1})
    current_group_ids = set(user.get("groups", []))

    new_group_ids = [group["_id"] for group in groups if group["_id"] not in current_group_ids]

    if new_group_ids:
        await db.client.groups.update_many(
            {"_id": {"$in": new_group_ids}},
            {"$addToSet": {"users": ObjectId(user_id)}}
        )

        updated_group_ids = list(current_group_ids.union(new_group_ids))
        await db.client.users.update_one(user_query, {"$set": {"groups": updated_group_ids}})


async def create_group_if_not_exists(db: DBSession, group_info: Group) -> None:
    query = {"name": group_info.name}
    group = await db.client.groups.find_one(query)

    if group is None:
        await db.client.groups.insert_one(group_info.model_dump(by_alias=True))


async def remove_user_from_all_groups(db: DBSession, user_id: Id) -> None:
    query = {"_id": ObjectId(user_id)}
    user = await db.client.users.find_one(query, {"groups": 1})

    if user is None:
        return

    group_ids = user.get("groups", [])
    if not group_ids:
        return

    await db.client.groups.update_many(
        {"_id": {"$in": group_ids}},
        {"$pull": {"users": ObjectId(user_id)}}
    )

    await db.client.users.update_one(query, {"$set": {"groups": []}})


async def set_login_date_for_user(db: DBSession, user_id: Id) -> None:
    query = {"_id": ObjectId(user_id)}, {"$set": {"last_login": datetime.now(timezone.utc)}}
    await db.client.users.update_one(*query)


async def remove_user_idm_data(db: DBSession, user_id: Id, provider: str) -> None:
    query = {"_id": ObjectId(user_id)}, {"$unset": {f"idm_data.{provider}": ""}}
    await db.client.users.update_one(*query)


async def get_username_by_id(db: DBSession, user_id: Id) -> Optional[str]:
    query = {"_id": ObjectId(user_id)}
    user = await db.client.users.find_one(query, {"username": 1})

    if user is None:
        return None

    return user.get("username")


async def get_user_preferences(db: DBSession, user_id: Id, name: str = None) -> Optional[list[PlatformPreferenceModel]]:
    query = {"_id": ObjectId(user_id)}
    user = await db.client.users.find_one(query)

    if user is None:
        return None

    if name is None:
        return UserModel.model_validate(user).preferences
    else:
        for preference in UserModel.model_validate(user).preferences:
            if preference.name == name:
                preference = PlatformPreferenceModel(**preference.model_dump())
                return [preference]


async def set_user_preferences(db: DBSession, user_id: Id, preferences: list[PlatformPreferenceModel]) -> None:
    query = {"_id": ObjectId(user_id)}, {"$set": {"preferences": [pref.model_dump() for pref in preferences]}}
    await db.client.users.update_one(*query)


async def get_group_by_name(db: DBSession, name: str) -> Optional[Group]:
    query = {"name": name}
    group = await db.client.groups.find_one(query)
    if group is None:
        return None

    return GroupModel.model_validate(group)


async def get_group_by_id(db: DBSession, group_id: Id) -> Optional[Group]:
    query = {"_id": ObjectId(group_id)}
    group = await db.client.groups.find_one(query)
    if group is None:
        return None

    return GroupModel.model_validate(group)


async def get_all_groups(db: DBSession) -> list[Group]:
    groups = await db.client.groups.find().to_list()
    return [GroupModel.model_validate(group) for group in groups]


async def get_all_users(db: DBSession):
    users = await db.client.users.find().to_list()
    return [UserModel.model_validate(user) for user in users]


async def get_all_parent_groups_from_child(db: DBSession, child_group_id: Id) -> list[Group]:
    child = await db.client.groups.find_one({"_id": child_group_id}, {"path": 1})
    if not child or "path" not in child:
        return []

    parent_ids = child["path"]

    cursor = db.client.groups.find({"_id": {"$in": parent_ids}})
    parents = await cursor.to_list(None)

    return [GroupModel.model_validate(parent) for parent in parents]


async def get_all_user_groups(db: DBSession, user: UserAll) -> list[Group]:
    groups = []
    for group_id in user.groups:
        groups += await get_all_parent_groups_from_child(db, group_id)

    return groups


async def get_top_group_organization(db: DBSession, group: Group) -> Optional[Group]:
    if not group.is_organization:
        return None

    org_id = group.path[0]

    if org_id == group.id:
        return group

    return await get_group_by_id(db, org_id)


async def create_group_db(db: DBSession, group_info: GroupCreate) -> GroupModel:
    group_id = ObjectId()
    group_created = GroupModel(
        _id=group_id,
        name=group_info.name,
        codename=group_info.codename,
        users=group_info.users,
        group_permissions=[],
        is_organization=False,
        path=[group_id]
    )

    await db.client.groups.insert_one(group_created.model_dump(by_alias=True))
    return group_created


async def add_group_to_users(db: DBSession, group_id: Id, users: list[Id]) -> None:
    await db.client.users.update_many(
        {"_id": {"$in": users}},
        {"$addToSet": {"groups": group_id}}
    )


async def remove_group_to_users(db: DBSession, group_id: Id, users: list[Id]) -> None:
    await db.client.users.update_many(
        {"_id": {"$in": users}},
        {"$pull": {"groups": group_id}}
    )


async def update_group(db: DBSession, group: Group) -> None:
    from wirecloud.commons.search import add_group_to_index
    query = {"_id": ObjectId(group.id)}

    data = group.model_dump(by_alias=True)
    await db.client.groups.update_one(query, {"$set": data})
    await add_group_to_index(group)


async def update_path_for_descendants(db: DBSession, group: Group) -> None:
    group_id = ObjectId(group.id)
    await db.client.groups.update_many(
        {
            "path": group_id,
            "_id": {"$ne": group_id},
        },
        [
            {
                "$set": {
                    "path": {
                        "$filter": {
                            "input": "$path",
                            "as": "p",
                            "cond": {"$ne": ["$$p", group_id]}
                        }
                    }
                }
            }
        ]
    )


async def delete_group(db: DBSession, group: Group, skip_descendants: bool = False) -> None:
    from wirecloud.commons.search import delete_group_from_index
    await remove_group_to_users(db, group.id, group.users)

    if not skip_descendants:
        await update_path_for_descendants(db, group)

    query_delete = {"_id": ObjectId(group.id)}
    await db.client.groups.delete_one(query_delete)
    await delete_group_from_index(group)


async def create_organization_db(db: DBSession, org_info: OrganizationCreate) -> GroupModel:
    org_id = ObjectId()
    org_created = GroupModel(
        _id=org_id,
        name=org_info.name,
        codename=org_info.codename,
        users=org_info.users,
        group_permissions=[],
        is_organization=True,
        path=[org_id]
    )

    await db.client.groups.insert_one(org_created.model_dump(by_alias=True))
    return org_created


async def delete_organization(db: DBSession, organization: Group) -> None:
    from wirecloud.commons.search import delete_group_from_index
    groups = await db.client.groups.find({"path": organization.id}).to_list(None)

    if not groups:
        return

    groups_ids = [group["_id"] for group in groups]
    await db.client.groups.delete_many({"_id": {"$in": groups_ids}})
    for group in groups:
        await remove_group_to_users(db, group["_id"], group["users"])
        await delete_group_from_index(GroupModel.model_validate(group))


async def get_all_organization_groups(db: DBSession, organization_group: Group) -> list[Group]:
    groups = await db.client.groups.find({"path": organization_group.id}).to_list(None)
    return [GroupModel.model_validate(group) for group in groups]
