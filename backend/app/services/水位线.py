"""水位线读写辅助（主逻辑在装载/热度窗）。"""


def 读(conn, 房间键: str):
    return conn.execute("SELECT * FROM 水位线 WHERE 房间键=?", (房间键,)).fetchone()
