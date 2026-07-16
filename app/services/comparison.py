from app.models.daily_user import DailyUser


def find_deleted_users(
    previous_users: list[DailyUser],
    current_users: list[dict[str, str | None]],
) -> list[DailyUser]:
    current_usernames = {user["username"] for user in current_users}
    return [user for user in previous_users if user.username not in current_usernames]


def find_new_users(
    previous_users: list[DailyUser],
    current_users: list[dict[str, str | None]],
) -> list[dict[str, str | None]]:
    previous_usernames = {user.username for user in previous_users}
    return [user for user in current_users if user["username"] not in previous_usernames]


def normalize_category(category: str | None) -> str:
    value = (category or "").strip().lower()
    if "advanced" in value:
        return "advanced_users"
    if "core" in value:
        return "core_users"
    if "self-service" in value or "self service" in value:
        return "self_service_users"
    return "other_users"


def find_classification_movements(
    previous_users: list[DailyUser],
    current_users: list[dict[str, str | None]],
) -> list[dict[str, str | None]]:
    previous_by_username = {user.username: user for user in previous_users}
    movements = []

    for current_user in current_users:
        previous_user = previous_by_username.get(current_user["username"])
        if not previous_user:
            continue

        if normalize_category(previous_user.category) == normalize_category(current_user["category"]):
            continue

        movements.append(
            {
                "username": current_user["username"],
                "user_id": current_user.get("user_id"),
                "full_name": current_user.get("full_name"),
                "from_category": previous_user.category,
                "to_category": current_user["category"],
            }
        )

    return movements
