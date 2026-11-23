from app.db import 连接
from app.seed import 此刻
from app.services import 入流闸


def 跑贯验() -> dict:
    """与入流/升格同持入流闸，拿到一致快照再互证。"""
    with 入流闸.闸:
        return _跑贯验()


def _跑贯验() -> dict:
    """窗输出与撤回/升格互证：已关闭窗的点赞/送礼须等于窗内事件合计；撤回后版本与末次撤回一致；
    升格须四方同态（匣已升格↔回执↔事件已升格挂目标窗），不得半截分叉。"""
    conn = 连接()
    try:
        问题 = []
        事件数 = conn.execute("SELECT COUNT(*) FROM 互动事件").fetchone()[0]
        已关闭 = conn.execute("SELECT * FROM 热度窗 WHERE 状态='已关闭'").fetchall()
        撤回数 = conn.execute("SELECT COUNT(*) FROM 撤回单").fetchone()[0]
        旁路数 = conn.execute("SELECT COUNT(*) FROM 旁路匣").fetchone()[0]

        for 窗 in 已关闭:
            agg = conn.execute(
                """SELECT COALESCE(SUM(点赞增量),0) AS 赞, COALESCE(SUM(送礼额),0) AS 送, COUNT(*) AS n
                   FROM 互动事件 WHERE 窗键=? AND 命运 IN ('已入窗','已升格')""",
                (窗["窗键"],),
            ).fetchone()
            if agg["赞"] != 窗["点赞合计"] or agg["送"] != 窗["送礼合计"]:
                问题.append(
                    f"窗{窗['窗键']}合计不符: 窗表赞{窗['点赞合计']}/送{窗['送礼合计']} vs 事件赞{agg['赞']}/送{agg['送']}"
                )
            if agg["n"] != 窗["事件笔数"]:
                问题.append(f"窗{窗['窗键']}笔数不符: 窗表{窗['事件笔数']} vs 事件{agg['n']}")

            末撤 = conn.execute(
                "SELECT * FROM 撤回单 WHERE 窗键=? ORDER BY 编号 DESC LIMIT 1",
                (窗["窗键"],),
            ).fetchone()
            if 末撤 and (末撤["新点赞"] != 窗["点赞合计"] or 末撤["新送礼"] != 窗["送礼合计"]):
                问题.append(f"窗{窗['窗键']}末次撤回与窗表不一致")

        # 旁路事件不得挂窗键
        脏旁路 = conn.execute(
            "SELECT COUNT(*) FROM 互动事件 WHERE 命运='已旁路' AND 窗键!=''"
        ).fetchone()[0]
        if 脏旁路:
            问题.append(f"旁路事件仍挂窗键:{脏旁路}")

        # 升格半截分叉：匣/回执/事件三方必须同态
        for 匣 in conn.execute("SELECT * FROM 旁路匣 WHERE 状态='已升格'").fetchall():
            回执 = conn.execute(
                "SELECT * FROM 升格回执 WHERE 旁路编号=?", (匣["编号"],)
            ).fetchone()
            if not 回执:
                问题.append(f"旁路匣{匣['编号']}已升格但无回执")
                continue
            ev = conn.execute(
                "SELECT * FROM 互动事件 WHERE 事件编号=?", (回执["事件编号"],)
            ).fetchone()
            if not ev or ev["命运"] != "已升格" or ev["窗键"] != 回执["目标窗键"]:
                问题.append(f"旁路匣{匣['编号']}已升格但事件未入目标窗{回执['目标窗键']}")
        for r in conn.execute(
            """SELECT r.* FROM 升格回执 r LEFT JOIN 旁路匣 b ON b.编号=r.旁路编号
               WHERE b.编号 IS NULL OR b.状态!='已升格'"""
        ).fetchall():
            问题.append(f"回执{r['编号']}存在但旁路匣{r['旁路编号']}未标已升格")
        孤升 = conn.execute(
            """SELECT COUNT(*) FROM 互动事件 e WHERE e.命运='已升格'
               AND NOT EXISTS (SELECT 1 FROM 升格回执 r WHERE r.事件编号=e.事件编号)"""
        ).fetchone()[0]
        if 孤升:
            问题.append(f"事件已升格但无回执:{孤升}")

        通过 = 1 if not 问题 else 0
        说明 = "窗输出与事件/撤回/升格互证通过" if 通过 else "；".join(问题)[:800]
        conn.execute(
            """INSERT INTO 窗贯验(时刻,事件数,已关闭窗数,撤回数,旁路数,是否通过,说明)
               VALUES (?,?,?,?,?,?,?)""",
            (此刻(), 事件数, len(已关闭), 撤回数, 旁路数, 通过, 说明),
        )
        conn.commit()
        return {
            "是否通过": bool(通过),
            "事件数": 事件数,
            "已关闭窗数": len(已关闭),
            "撤回数": 撤回数,
            "旁路数": 旁路数,
            "说明": 说明,
            "问题": 问题,
        }
    finally:
        conn.close()
