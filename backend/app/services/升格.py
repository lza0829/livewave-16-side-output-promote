"""旁路升格：把旁路匣中的载荷升格为正式热度窗结果。

口径（关键设计取舍，全局唯一）：**只写入升格时刻新窗**
- 目标窗键 = 升格处理时「事件时水位」所在窗。水位必小于其所在窗的窗止，
  故目标窗恒为开启窗，天然不碰历史已关窗；
- 历史已关窗合计禁止增加：原窗键只读记录于回执，绝不写回，不写撤回单
  （撤回单专属「迟到修正」）；
- 匣标「已升格」，事件命运 →「已升格」、窗键 → 目标窗键。

对偶口径「写回原窗键＋撤回/修正」不实现。两口径对「升格完成后原窗键合计
是否变大」结论相反，只读接口的「原窗合计是否变」字段使二者可区分
（本口径恒 False）。

不变量（失败闭）：
- 匣状态与窗合计同成败：闸内单事务，任一环节失败整体回滚；
- 重复升格不双计：匣状态闸＋升格回执 UNIQUE(旁路编号)，重放只回执不重复计窗；
- 与入流/关窗扫描互斥：同持 app.services.入流闸，不得半截分叉。
"""

import json

from app.db import 连接
from app.seed import 此刻
from app.services import 入流闸, 时间

口径 = "只写升格时刻新窗"


class 旁路不存在(Exception):
    pass


class 升格拒绝(Exception):
    """站规禁止或状态分叉：拒绝升格，已回滚，无副作用。"""


def 升格一笔(旁路编号: int) -> dict:
    """把一条旁路载荷升格进水位所在新窗。幂等：已升格则只回执不重复计窗。"""
    with 入流闸.闸:
        conn = 连接()
        try:
            站 = {r["键"]: r["值"] for r in conn.execute("SELECT 键, 值 FROM 站规")}
            if 站.get("允许升格", "是") != "是":
                raise 升格拒绝("站规未允许升格")
            窗长 = int(站.get("窗长秒", "60"))

            匣 = conn.execute("SELECT * FROM 旁路匣 WHERE 编号=?", (旁路编号,)).fetchone()
            if not 匣:
                raise 旁路不存在(f"旁路匣无此编号:{旁路编号}")
            if 匣["状态"] == "已升格":
                # 幂等重放：回既有回执，绝不再动窗合计
                回执 = conn.execute(
                    "SELECT * FROM 升格回执 WHERE 旁路编号=?", (旁路编号,)
                ).fetchone()
                if not 回执:
                    raise 升格拒绝(f"旁路{旁路编号}已升格但回执缺失，半截状态，拒绝重放")
                return {**_回执视图(conn, 回执), "重复": True}

            载荷 = json.loads(匣["载荷"])
            事件编号 = 载荷.get("事件编号")
            ev = (
                conn.execute(
                    "SELECT * FROM 互动事件 WHERE 事件编号=?", (事件编号,)
                ).fetchone()
                if 事件编号
                else None
            )
            if not ev or ev["命运"] != "已旁路":
                raise 升格拒绝(f"旁路{旁路编号}载荷事件未处于已旁路，不可升格")
            房间键 = ev["房间键"]
            水位 = conn.execute(
                "SELECT * FROM 水位线 WHERE 房间键=?", (房间键,)
            ).fetchone()
            if not 水位:
                raise 升格拒绝(f"房间{房间键}无水位线，拒绝升格")

            原窗键 = 时间.窗键(房间键, 时间.对齐窗起(ev["事件时"], 窗长))
            目标窗起 = 时间.对齐窗起(水位["事件时水位"], 窗长)
            目标窗键 = 时间.窗键(房间键, 目标窗起)
            if 目标窗键 == 原窗键:
                # 防御：已旁路事件的水位必已越过 原窗止+允许迟到，不可能落回原窗
                raise 升格拒绝("目标窗与原窗相同，状态分叉，拒绝升格")

            窗 = conn.execute("SELECT * FROM 热度窗 WHERE 窗键=?", (目标窗键,)).fetchone()
            if not 窗:
                conn.execute(
                    """INSERT INTO 热度窗(窗键,房间键,窗起事件时,窗止事件时,状态,点赞合计,送礼合计,事件笔数,版本)
                       VALUES (?,?,?,?, '开启', 0, 0, 0, 0)""",
                    (目标窗键, 房间键, 目标窗起, 时间.加秒(目标窗起, 窗长)),
                )
            elif 窗["状态"] != "开启":
                # 理论不可达：水位所在窗必开；一旦出现即状态分叉，失败闭
                raise 升格拒绝(f"目标窗{目标窗键}已关闭，拒绝升格")

            赞, 送 = int(ev["点赞增量"]), int(ev["送礼额"])
            时刻 = 此刻()
            conn.execute(
                "UPDATE 热度窗 SET 点赞合计=点赞合计+?, 送礼合计=送礼合计+?, 事件笔数=事件笔数+1 WHERE 窗键=?",
                (赞, 送, 目标窗键),
            )
            r1 = conn.execute(
                "UPDATE 互动事件 SET 命运='已升格', 窗键=? WHERE 事件编号=? AND 命运='已旁路'",
                (目标窗键, 事件编号),
            )
            r2 = conn.execute(
                "UPDATE 旁路匣 SET 状态='已升格', 升格时刻=? WHERE 编号=? AND 状态='未处理'",
                (时刻, 旁路编号),
            )
            if r1.rowcount != 1 or r2.rowcount != 1:
                raise 升格拒绝("状态迁移行数异常，已回滚")
            conn.execute(
                """INSERT INTO 升格回执(旁路编号,事件编号,房间键,原窗键,目标窗键,点赞,送礼,口径,原窗合计变,升格时刻)
                   VALUES (?,?,?,?,?,?,?,?,0,?)""",
                (旁路编号, 事件编号, 房间键, 原窗键, 目标窗键, 赞, 送, 口径, 时刻),
            )
            conn.commit()
            回执 = conn.execute(
                "SELECT * FROM 升格回执 WHERE 旁路编号=?", (旁路编号,)
            ).fetchone()
            return {**_回执视图(conn, 回执), "重复": False}
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def 列升格() -> list:
    """升格只读接口：旁路编号/原窗键/目标窗键/原窗合计是否变/valid，逐条实时复核。"""
    conn = 连接()
    try:
        rows = conn.execute("SELECT * FROM 升格回执 ORDER BY 编号 DESC").fetchall()
        return [_回执视图(conn, r) for r in rows]
    finally:
        conn.close()


def 取升格(旁路编号: int) -> dict | None:
    conn = 连接()
    try:
        回执 = conn.execute(
            "SELECT * FROM 升格回执 WHERE 旁路编号=?", (旁路编号,)
        ).fetchone()
        return _回执视图(conn, 回执) if 回执 else None
    finally:
        conn.close()


def _校验(conn, 回执) -> tuple[bool, str]:
    """四方同态复核：匣已升格 ↔ 回执 ↔ 事件已升格且挂目标窗 ↔ 目标窗存在。"""
    匣 = conn.execute("SELECT * FROM 旁路匣 WHERE 编号=?", (回执["旁路编号"],)).fetchone()
    if not 匣 or 匣["状态"] != "已升格":
        return False, "旁路匣未标已升格"
    ev = conn.execute(
        "SELECT * FROM 互动事件 WHERE 事件编号=?", (回执["事件编号"],)
    ).fetchone()
    if not ev or ev["命运"] != "已升格":
        return False, "事件未标已升格"
    if ev["窗键"] != 回执["目标窗键"]:
        return False, "事件窗键与目标窗不符"
    if not conn.execute("SELECT 1 FROM 热度窗 WHERE 窗键=?", (回执["目标窗键"],)).fetchone():
        return False, "目标窗不存在"
    if 回执["原窗合计变"]:
        return False, "口径冲突：本实现只写新窗，原窗合计不得变"
    return True, "匣/事件/回执/窗四方一致"


def _回执视图(conn, 回执) -> dict:
    valid, 说明 = _校验(conn, 回执)
    return {
        "回执编号": 回执["编号"],
        "旁路编号": 回执["旁路编号"],
        "事件编号": 回执["事件编号"],
        "房间键": 回执["房间键"],
        "原窗键": 回执["原窗键"],
        "目标窗键": 回执["目标窗键"],
        "点赞": 回执["点赞"],
        "送礼": 回执["送礼"],
        "口径": 回执["口径"],
        "原窗合计是否变": bool(回执["原窗合计变"]),
        "升格时刻": 回执["升格时刻"],
        "valid": valid,
        "校验说明": 说明,
    }
