from app.models.daily_user import DailyUser


def find_deleted_users(
    previous_users: list[DailyUser],
    current_users: list[dict[str, str | None]],
) -> list[DailyUser]:
    current_usernames = {user["username"] for user in current_users}
    return [user for user in previous_users if user.username not in current_usernames]
