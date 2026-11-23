"""旁路升格夹具：三段硬推理验证 + 失败闭用例。

夹具一  对已旁路事件升格：乙口径下原窗合计不变、新窗可查（原窗合计是否变=False）；
夹具二  重复升格：回执唯一，窗合计不得双计；
夹具三  升格与入流/关窗扫描并发：匣与窗不得半截分叉，贯验须通过；
补      站规禁止 / 未知直播间旁路：拒绝升格且无副作用（失败闭）。

可直接运行：python3 tests/test_升格.py；亦兼容 pytest。
"""

import json
import os
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["数据目录"] = tempfile.mkdtemp(prefix="播浪升格测-")  # 须先于 app 导入

from app import db, seed  # noqa: E402
from app.services import 装载, 升格, 贯验  # noqa: E402

夹具目录 = Path(__file__).resolve().parent.parent.parent / "fixtures"


def 新库():
    d = tempfile.mkdtemp(prefix="播浪升格测-")
    db.数据目录 = Path(d)
    db.库路径 = Path(d) / "播浪.db"
    seed.初始化库()


def 装夹具(名):
    装载.装一批(json.loads((夹具目录 / f"{名}.json").read_text(encoding="utf-8")))


def 查一行(sql, 参=()):
    conn = db.连接()
    try:
        return conn.execute(sql, 参).fetchone()
    finally:
        conn.close()


def 找旁路(事件编号):
    conn = db.连接()
    try:
        for r in conn.execute("SELECT * FROM 旁路匣").fetchall():
            if json.loads(r["载荷"]).get("事件编号") == 事件编号:
                return dict(r)
        return None
    finally:
        conn.close()


def 窗合计(窗键):
    w = 查一行("SELECT * FROM 热度窗 WHERE 窗键=?", (窗键,))
    return (w["点赞合计"], w["送礼合计"], w["事件笔数"]) if w else None


def test_升格写新窗不改原窗():
    """夹具一：乙口径——原窗合计不变，新窗可查；只读接口 原窗合计是否变=False。"""
    新库()
    装夹具("旁路升格样例")
    匣 = 找旁路("P3")
    assert 匣 and 匣["状态"] == "未处理", f"布景失败:{匣}"

    原窗键 = "房A|2026-11-22T13:00:00Z"   # P3 事件时 13:00:50 所属窗（已关闭）
    目标窗键 = "房A|2026-11-22T13:02:00Z"  # 水位 13:02:40 所在窗（开启，含 P2 赞1）
    原窗前 = 窗合计(原窗键)
    assert 原窗前 == (2, 0, 1), f"原窗布景不符:{原窗前}"
    assert 查一行("SELECT 状态 FROM 热度窗 WHERE 窗键=?", (原窗键,))["状态"] == "已关闭"

    回执 = 升格.升格一笔(匣["编号"])
    assert 回执["重复"] is False
    assert 回执["原窗键"] == 原窗键, 回执
    assert 回执["目标窗键"] == 目标窗键, 回执
    assert 回执["原窗合计是否变"] is False, "乙口径下原窗合计不得变"
    assert 回执["口径"] == 升格.口径 == "只写升格时刻新窗"
    assert 回执["valid"] is True, 回执["校验说明"]

    assert 窗合计(原窗键) == 原窗前, "历史已关窗合计禁止增加"
    assert 窗合计(目标窗键) == (1 + 7, 0 + 3, 1 + 1), "新窗须含 P2 与升格载荷"
    ev = 查一行("SELECT * FROM 互动事件 WHERE 事件编号='P3'")
    assert ev["命运"] == "已升格" and ev["窗键"] == 目标窗键
    assert 查一行("SELECT 状态 FROM 旁路匣 WHERE 编号=?", (匣["编号"],))["状态"] == "已升格"

    接口 = 升格.取升格(匣["编号"])
    assert 接口 and 接口["valid"] is True and 接口["原窗合计是否变"] is False
    assert 贯验.跑贯验()["是否通过"], "升格后窗互证须通过"


def test_重复升格不双计():
    """夹具二：重复升格——回执唯一，窗合计不得双计。"""
    新库()
    装夹具("旁路升格样例")
    匣 = 找旁路("P3")
    目标窗键 = "房A|2026-11-22T13:02:00Z"

    一 = 升格.升格一笔(匣["编号"])
    首计 = 窗合计(目标窗键)
    for _ in range(3):
        再 = 升格.升格一笔(匣["编号"])
        assert 再["重复"] is True and 再["回执编号"] == 一["回执编号"]
        assert 再["valid"] is True
    assert 窗合计(目标窗键) == 首计, "重复升格不得再动窗合计"
    assert 查一行("SELECT COUNT(*) c FROM 升格回执 WHERE 旁路编号=?", (匣["编号"],))["c"] == 1
    assert 贯验.跑贯验()["是否通过"]


def test_并发升格与入流无半截():
    """夹具三：升格×入流/关窗扫描并发——不得匣与窗半截分叉。"""
    新库()
    布景事件 = [
        {"事件编号": "C0", "房间键": "房A", "事件类型": "点赞",
         "事件时": "2026-11-22T14:00:05Z", "处理时": "2026-11-22T14:00:06Z", "点赞增量": 1, "送礼额": 0},
        {"事件编号": "C1", "房间键": "房A", "事件类型": "点赞",
         "事件时": "2026-11-22T14:05:00Z", "处理时": "2026-11-22T14:05:01Z", "点赞增量": 1, "送礼额": 0},
    ] + [
        {"事件编号": f"CL{i}", "房间键": "房A", "事件类型": "点赞",
         "事件时": f"2026-11-22T14:00:{10 + i:02d}Z", "处理时": "2026-11-22T14:05:05Z",
         "点赞增量": i + 1, "送礼额": 0}
        for i in range(6)
    ]
    报 = 装载.装一批({"批次编号": "批-并发-布景", "事件": 布景事件})
    assert 报["旁路"] == 6, f"布景旁路数不符:{报}"
    conn = db.连接()
    try:
        匣们 = [r["编号"] for r in conn.execute("SELECT 编号 FROM 旁路匣").fetchall()]
    finally:
        conn.close()
    assert len(匣们) == 6

    错误 = []

    def 升格工():
        for _ in range(3):
            for n in 匣们:
                try:
                    升格.升格一笔(n)
                except Exception as e:  # noqa: BLE001
                    错误.append(("升格", n, repr(e)))

    def 入流工():
        for i in range(10):
            try:
                装载.装一批({"批次编号": f"批-并发-{i}", "事件": [
                    {"事件编号": f"CN{i}", "房间键": "房A", "事件类型": "点赞",
                     "事件时": f"2026-11-22T14:{6 + i:02d}:10Z",
                     "处理时": f"2026-11-22T14:{6 + i:02d}:11Z", "点赞增量": 1, "送礼额": 0},
                ]})
            except Exception as e:  # noqa: BLE001
                错误.append(("入流", i, repr(e)))

    def 贯验工():
        for _ in range(5):
            try:
                贯验.跑贯验()
            except Exception as e:  # noqa: BLE001
                错误.append(("贯验", repr(e)))

    线程 = [threading.Thread(target=升格工) for _ in range(2)]
    线程 += [threading.Thread(target=入流工), threading.Thread(target=贯验工)]
    for t in 线程:
        t.start()
    for t in 线程:
        t.join()
    assert not 错误, f"并发执行出错:{错误[:5]}"

    # 每匣：恰一条回执，匣/事件/回执同态
    conn = db.连接()
    try:
        for n in 匣们:
            匣 = conn.execute("SELECT * FROM 旁路匣 WHERE 编号=?", (n,)).fetchone()
            assert 匣["状态"] == "已升格", f"匣{n}未处理但已无可升"
            回执 = conn.execute("SELECT * FROM 升格回执 WHERE 旁路编号=?", (n,)).fetchall()
            assert len(回执) == 1, f"匣{n}回执数{len(回执)}，双计！"
            ev = conn.execute(
                "SELECT * FROM 互动事件 WHERE 事件编号=?", (回执[0]["事件编号"],)
            ).fetchone()
            assert ev["命运"] == "已升格" and ev["窗键"] == 回执[0]["目标窗键"], f"匣{n}半截分叉"
        # 全部窗（含开启）：窗表合计 == 窗内事件合计
        for 窗 in conn.execute("SELECT * FROM 热度窗").fetchall():
            agg = conn.execute(
                """SELECT COALESCE(SUM(点赞增量),0) z, COALESCE(SUM(送礼额),0) s, COUNT(*) n
                   FROM 互动事件 WHERE 窗键=? AND 命运 IN ('已入窗','已升格')""",
                (窗["窗键"],),
            ).fetchone()
            assert (agg["z"], agg["s"], agg["n"]) == (
                窗["点赞合计"], 窗["送礼合计"], 窗["事件笔数"]
            ), f"窗{窗['窗键']}合计分叉"
    finally:
        conn.close()
    assert all(r["valid"] for r in 升格.列升格()), "并发后回执须全部 valid"
    验 = 贯验.跑贯验()
    assert 验["是否通过"], f"并发后贯验须通过:{验['说明']}"


def test_站规禁止升格失败闭():
    新库()
    装夹具("旁路升格样例")
    匣 = 找旁路("P3")
    conn = db.连接()
    try:
        conn.execute("UPDATE 站规 SET 值='否' WHERE 键='允许升格'")
        conn.commit()
    finally:
        conn.close()
    try:
        升格.升格一笔(匣["编号"])
        raise AssertionError("站规禁止时升格须被拒绝")
    except 升格.升格拒绝:
        pass
    assert 查一行("SELECT 状态 FROM 旁路匣 WHERE 编号=?", (匣["编号"],))["状态"] == "未处理"
    assert 查一行("SELECT COUNT(*) c FROM 升格回执")["c"] == 0
    assert 窗合计("房A|2026-11-22T13:02:00Z") == (1, 0, 1), "拒绝升格不得有副作用"


def test_未知直播间旁路不可升格():
    新库()
    装载.装一批({"批次编号": "批-未知房", "事件": [
        {"事件编号": "U1", "房间键": "房不存在", "事件类型": "点赞",
         "事件时": "2026-11-22T15:00:00Z", "处理时": "2026-11-22T15:00:01Z", "点赞增量": 5, "送礼额": 0},
    ]})
    匣 = 找旁路("U1")
    assert 匣 and 匣["原因"] == "未知直播间"
    try:
        升格.升格一笔(匣["编号"])
        raise AssertionError("未知直播间旁路须拒绝升格")
    except 升格.升格拒绝:
        pass
    assert 查一行("SELECT 状态 FROM 旁路匣 WHERE 编号=?", (匣["编号"],))["状态"] == "未处理"
    assert 查一行("SELECT COUNT(*) c FROM 升格回执")["c"] == 0


if __name__ == "__main__":
    用例 = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    败 = 0
    for f in 用例:
        try:
            f()
            print(f"通过 {f.__name__}")
        except Exception as e:  # noqa: BLE001
            败 += 1
            print(f"失败 {f.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(用例) - 败}/{len(用例)} 通过")
    sys.exit(1 if 败 else 0)
