from app.db import 连接


def 总览() -> dict:
    conn = 连接()
    try:
        def c(sql: str) -> int:
            return conn.execute(sql).fetchone()[0]

        末 = conn.execute(
            "SELECT * FROM 窗贯验 ORDER BY 编号 DESC LIMIT 1"
        ).fetchone()
        return {
            "直播间": c("SELECT COUNT(*) FROM 直播间"),
            "互动事件": c("SELECT COUNT(*) FROM 互动事件"),
            "已入窗": c("SELECT COUNT(*) FROM 互动事件 WHERE 命运='已入窗'"),
            "已旁路": c("SELECT COUNT(*) FROM 互动事件 WHERE 命运='已旁路'"),
            "撤回单数": c("SELECT COUNT(*) FROM 撤回单"),
            "开启窗": c("SELECT COUNT(*) FROM 热度窗 WHERE 状态='开启'"),
            "已关闭窗": c("SELECT COUNT(*) FROM 热度窗 WHERE 状态='已关闭'"),
            "撤回单": c("SELECT COUNT(*) FROM 撤回单"),
            "旁路匣": c("SELECT COUNT(*) FROM 旁路匣"),
            "装载批次": c("SELECT COUNT(*) FROM 装载批次"),
            "末次贯验": dict(末) if 末 else None,
        }
    finally:
        conn.close()
