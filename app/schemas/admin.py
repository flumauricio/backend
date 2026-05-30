from pydantic import BaseModel


class AdminStatsResponse(BaseModel):
    """
    Aggregate stats for the admin dashboard.
    All counts are integers — never null.
    Storage fields are in MB.
    """
    # Users
    users_total:    int
    users_active:   int
    users_inactive: int

    # Plans
    plans_total:    int
    plans_active:   int

    # Bots — by status
    bots_total:     int
    bots_running:   int
    bots_stopped:   int
    bots_error:     int
    bots_draft:     int
    bots_starting:  int
    bots_stopping:  int

    # Capacity estimates (MB) — derived from user limits / plans
    estimated_cloud_storage_mb: int
    estimated_bot_storage_mb:   int
    estimated_ram_reserved_mb:  int
