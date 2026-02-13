"""Finance 工具 — 个人记账管理。

支持动作：
- add_transaction: 添加收支记录
- query_transactions: 查询收支记录
- get_financial_summary: 财务汇总统计
- update_transaction: 更新收支记录
- delete_transaction: 删除收支记录

借鉴来源：参考项目_changoai/backend/tool_functions.py 记账管理相关函数
存储位置：~/.winclaw/winclaw_tools.db（transactions 表）
金额单位：内部以"分"存储（避免浮点精度问题），对外以"元"交互
"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Generator

from src.tools.base import ActionDef, BaseTool, ToolResult, ToolResultStatus

logger = logging.getLogger(__name__)

_DEFAULT_DB = Path.home() / ".winclaw" / "winclaw_tools.db"


class FinanceTool(BaseTool):
    """个人记账管理工具。

    支持收入/支出记录的 CRUD 和按周期汇总统计。
    金额内部以分(整数)存储，对外以元(浮点)展示。
    """

    name = "finance"
    emoji = "💰"
    title = "记账管理"
    description = "记录收支、查询账单、财务汇总统计"

    def __init__(self, db_path: str = ""):
        super().__init__()
        self._db_path = Path(db_path) if db_path else _DEFAULT_DB
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(str(self._db_path))
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    transaction_date TEXT NOT NULL,
                    type TEXT NOT NULL CHECK(type IN ('income','expense')),
                    amount_cents INTEGER NOT NULL,
                    category TEXT NOT NULL DEFAULT '其他',
                    description TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_transactions_date
                ON transactions(transaction_date DESC)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_transactions_type
                ON transactions(type)
            """)
            conn.commit()

    # ------------------------------------------------------------------

    def get_actions(self) -> list[ActionDef]:
        return [
            ActionDef(
                name="add_transaction",
                description="添加一笔收支记录",
                parameters={
                    "type": {
                        "type": "string",
                        "description": "类型: income（收入）或 expense（支出）",
                    },
                    "amount": {
                        "type": "number",
                        "description": "金额（元），如 12.50",
                    },
                    "category": {
                        "type": "string",
                        "description": "分类，如 餐饮/交通/工资/购物 等",
                    },
                    "description": {
                        "type": "string",
                        "description": "备注说明（可选）",
                    },
                    "date": {
                        "type": "string",
                        "description": "日期 YYYY-MM-DD（可选，默认今天）",
                    },
                },
                required_params=["type", "amount", "category"],
            ),
            ActionDef(
                name="query_transactions",
                description="查询收支记录，支持按时间范围/类型/分类筛选",
                parameters={
                    "date_range": {
                        "type": "string",
                        "description": "时间范围: today/week/month/year/all，默认 month",
                    },
                    "type": {
                        "type": "string",
                        "description": "类型筛选: income/expense（可选）",
                    },
                    "category": {
                        "type": "string",
                        "description": "分类筛选（可选）",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回数量，默认 20",
                    },
                },
                required_params=[],
            ),
            ActionDef(
                name="get_financial_summary",
                description="获取财务汇总统计（总收入、总支出、结余、分类占比）",
                parameters={
                    "period": {
                        "type": "string",
                        "description": "统计周期: today/week/month/year/all，默认 month",
                    },
                },
                required_params=[],
            ),
            ActionDef(
                name="update_transaction",
                description="更新收支记录",
                parameters={
                    "transaction_id": {
                        "type": "integer",
                        "description": "记录 ID",
                    },
                    "amount": {
                        "type": "number",
                        "description": "新金额（可选）",
                    },
                    "category": {
                        "type": "string",
                        "description": "新分类（可选）",
                    },
                    "description": {
                        "type": "string",
                        "description": "新备注（可选）",
                    },
                },
                required_params=["transaction_id"],
            ),
            ActionDef(
                name="delete_transaction",
                description="删除收支记录",
                parameters={
                    "transaction_id": {
                        "type": "integer",
                        "description": "记录 ID",
                    },
                },
                required_params=["transaction_id"],
            ),
        ]

    async def execute(self, action: str, params: dict[str, Any]) -> ToolResult:
        handlers = {
            "add_transaction": self._add_transaction,
            "query_transactions": self._query_transactions,
            "get_financial_summary": self._get_financial_summary,
            "update_transaction": self._update_transaction,
            "delete_transaction": self._delete_transaction,
        }
        handler = handlers.get(action)
        if handler is None:
            return ToolResult(status=ToolResultStatus.ERROR, error=f"不支持的动作: {action}")
        try:
            return handler(params)
        except Exception as e:
            logger.error("记账操作失败: %s", e)
            return ToolResult(status=ToolResultStatus.ERROR, error=str(e))

    # ------------------------------------------------------------------

    def _add_transaction(self, params: dict[str, Any]) -> ToolResult:
        txn_type = params.get("type", "").strip()
        amount = params.get("amount", 0)
        category = params.get("category", "其他").strip()
        description = params.get("description", "").strip()
        date = params.get("date", "")

        if txn_type not in ("income", "expense"):
            return ToolResult(status=ToolResultStatus.ERROR, error="type 必须是 income 或 expense")
        if not isinstance(amount, (int, float)) or amount <= 0:
            return ToolResult(status=ToolResultStatus.ERROR, error="金额必须大于 0")

        amount_cents = int(round(amount * 100))
        if not date:
            date = datetime.now().strftime("%Y-%m-%d")
        now = datetime.now().isoformat()

        with self._conn() as conn:
            cursor = conn.execute("""
                INSERT INTO transactions
                (transaction_date, type, amount_cents, category, description, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (date, txn_type, amount_cents, category, description, now, now))
            conn.commit()
            tid = cursor.lastrowid

        type_icon = "💰" if txn_type == "income" else "💸"
        type_text = "收入" if txn_type == "income" else "支出"

        output = f"{type_text}已记录 (ID:{tid})\n{type_icon} ¥{amount:.2f} | 📂 {category} | 📅 {date}"
        if description:
            output += f"\n📝 {description}"

        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output=output,
            data={
                "transaction_id": tid, "type": txn_type, "amount": amount,
                "category": category, "date": date,
            },
        )

    def _query_transactions(self, params: dict[str, Any]) -> ToolResult:
        date_range = params.get("date_range", "month")
        txn_type = params.get("type", "")
        category = params.get("category", "")
        limit = min(params.get("limit", 20), 100)

        clauses: list[str] = []
        values: list[Any] = []
        today = datetime.now()

        date_map = {
            "today": 0, "week": 7, "month": 30, "year": 365,
        }
        if date_range in date_map:
            if date_range == "today":
                clauses.append("transaction_date = ?")
                values.append(today.strftime("%Y-%m-%d"))
            else:
                clauses.append("transaction_date >= ?")
                values.append((today - timedelta(days=date_map[date_range])).strftime("%Y-%m-%d"))

        if txn_type in ("income", "expense"):
            clauses.append("type = ?")
            values.append(txn_type)
        if category:
            clauses.append("category = ?")
            values.append(category)

        where = " AND ".join(clauses) if clauses else "1=1"
        sql = (
            f"SELECT id, transaction_date, type, amount_cents, category, description "
            f"FROM transactions WHERE {where} ORDER BY transaction_date DESC, id DESC LIMIT ?"
        )
        values.append(limit)

        with self._conn() as conn:
            rows = conn.execute(sql, values).fetchall()

        if not rows:
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output="未找到符合条件的收支记录。",
                data={"transactions": [], "count": 0},
            )

        lines = [f"找到 {len(rows)} 条记录："]
        data_list = []
        for i, (tid, tdate, ttype, cents, cat, desc) in enumerate(rows, 1):
            yuan = cents / 100
            icon = "💰" if ttype == "income" else "💸"
            sign = "+" if ttype == "income" else "-"
            lines.append(f"  {i}. {icon} {sign}¥{yuan:.2f} | 📂 {cat} | 📅 {tdate} (ID:{tid})")
            if desc:
                lines.append(f"      📝 {desc}")
            data_list.append({
                "id": tid, "date": tdate, "type": ttype,
                "amount": yuan, "category": cat, "description": desc,
            })

        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output="\n".join(lines),
            data={"transactions": data_list, "count": len(data_list)},
        )

    def _get_financial_summary(self, params: dict[str, Any]) -> ToolResult:
        period = params.get("period", "month")
        today = datetime.now()

        start_map = {
            "today": today.strftime("%Y-%m-%d"),
            "week": (today - timedelta(days=7)).strftime("%Y-%m-%d"),
            "month": (today - timedelta(days=30)).strftime("%Y-%m-%d"),
            "year": (today - timedelta(days=365)).strftime("%Y-%m-%d"),
        }
        start_date = start_map.get(period, "1900-01-01")

        with self._conn() as conn:
            # 总收入
            row = conn.execute(
                "SELECT COALESCE(SUM(amount_cents),0) FROM transactions "
                "WHERE type='income' AND transaction_date >= ?", (start_date,)
            ).fetchone()
            total_income_cents = row[0] if row else 0

            # 总支出
            row = conn.execute(
                "SELECT COALESCE(SUM(amount_cents),0) FROM transactions "
                "WHERE type='expense' AND transaction_date >= ?", (start_date,)
            ).fetchone()
            total_expense_cents = row[0] if row else 0

            # 分类支出
            cat_rows = conn.execute(
                "SELECT category, SUM(amount_cents) FROM transactions "
                "WHERE type='expense' AND transaction_date >= ? "
                "GROUP BY category ORDER BY SUM(amount_cents) DESC LIMIT 10",
                (start_date,)
            ).fetchall()

        income = total_income_cents / 100
        expense = total_expense_cents / 100
        balance = income - expense

        period_text = {"today": "今日", "week": "本周", "month": "本月", "year": "本年"}.get(period, "全部")

        lines = [
            f"{period_text}财务汇总",
            f"📊 统计周期: {start_date} 至 {today.strftime('%Y-%m-%d')}",
            f"💰 总收入: ¥{income:.2f}",
            f"💸 总支出: ¥{expense:.2f}",
            f"📈 结余: ¥{balance:.2f}",
        ]

        if cat_rows:
            lines.append("\n📂 支出分类占比：")
            for cat, cents in cat_rows:
                yuan = cents / 100
                pct = (yuan / expense * 100) if expense > 0 else 0
                lines.append(f"  • {cat}: ¥{yuan:.2f} ({pct:.1f}%)")

        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output="\n".join(lines),
            data={
                "period": period, "total_income": income,
                "total_expense": expense, "balance": balance,
                "expense_by_category": {cat: cents / 100 for cat, cents in cat_rows},
            },
        )

    def _update_transaction(self, params: dict[str, Any]) -> ToolResult:
        tid = params.get("transaction_id")
        if tid is None:
            return ToolResult(status=ToolResultStatus.ERROR, error="缺少 transaction_id")

        updates: dict[str, Any] = {}
        if "amount" in params and params["amount"]:
            updates["amount_cents"] = int(round(float(params["amount"]) * 100))
        if "category" in params and params["category"]:
            updates["category"] = params["category"]
        if "description" in params:
            updates["description"] = params["description"]

        if not updates:
            return ToolResult(status=ToolResultStatus.ERROR, error="没有可更新的字段")

        updates["updated_at"] = datetime.now().isoformat()
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [tid]

        with self._conn() as conn:
            cursor = conn.execute(f"UPDATE transactions SET {set_clause} WHERE id = ?", values)
            conn.commit()
            if cursor.rowcount == 0:
                return ToolResult(status=ToolResultStatus.ERROR, error=f"记录不存在: ID {tid}")

        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output=f"已更新记录 ID:{tid}",
            data={"transaction_id": tid, "updated_fields": list(updates.keys())},
        )

    def _delete_transaction(self, params: dict[str, Any]) -> ToolResult:
        tid = params.get("transaction_id")
        if tid is None:
            return ToolResult(status=ToolResultStatus.ERROR, error="缺少 transaction_id")

        with self._conn() as conn:
            row = conn.execute(
                "SELECT type, amount_cents, category, transaction_date FROM transactions WHERE id = ?",
                (tid,)
            ).fetchone()
            if not row:
                return ToolResult(status=ToolResultStatus.ERROR, error=f"记录不存在: ID {tid}")
            ttype, cents, cat, tdate = row
            conn.execute("DELETE FROM transactions WHERE id = ?", (tid,))
            conn.commit()

        icon = "💰" if ttype == "income" else "💸"
        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output=f"已删除记录: {icon} ¥{cents / 100:.2f} {cat} ({tdate})",
            data={"transaction_id": tid, "deleted": True},
        )
