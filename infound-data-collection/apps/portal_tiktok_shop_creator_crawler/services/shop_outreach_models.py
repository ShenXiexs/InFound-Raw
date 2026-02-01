from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, List


@dataclass
class AccountProfile:
    name: str
    login_email: str
    login_password: Optional[str]
    gmail_username: str
    gmail_app_password: str
    region: str
    creator_id: Optional[str] = None
    enabled: bool = True


@dataclass
class ShopOutreachOptions:
    region: str
    account_name: Optional[str] = None
    headless: Optional[bool] = None
    manual_login: Optional[bool] = None
    manual_email_code_input: Optional[bool] = None
    max_creators: int = 30
    search_strategy: Dict[str, Any] = field(default_factory=dict)
    export_enabled: bool = False
    export_dir: str = "data/shop_outreach"
    messages: Optional[List[Dict[str, Any]]] = None
    task_id: Optional[str] = None
    operator_id: Optional[str] = None
    brand_name: Optional[str] = None
