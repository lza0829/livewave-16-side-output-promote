import React, { useEffect, useState } from "react";
import { 取, 递 } from "../api.js";

export default function 旁路匣页() {
  const [行, 设] = useState([]);
  const [回执, 设回执] = useState([]);
  const [误, 设误] = useState("");
  const 刷 = () => {
    取("/旁路匣").then(设);
    取("/升格").then(设回执);
  };
  useEffect(() => { 刷(); }, []);
  const 升格 = async (旁路编号) => {
    设误("");
    try {
      await 递("/升格", { 旁路编号 });
    } catch (e) {
      设误(String(e.message || e));
    }
    刷();
  };
  return (
    <div>
      <h1 className="题">⑤ 旁路匣</h1>
      <p className="述">
        水位已越过「该事件所属窗的窗止 + 允许迟到」时，事件不得再改已关窗，落入旁路匣。侧输出，不是隔离金库。
        站规允许时可<strong>升格</strong>：载荷计入升格时刻水位所在新窗，历史已关窗合计不变；匣状态与窗合计同成败，重复升格不双计。
      </p>
      <div className="行"><button className="次" onClick={刷}>刷新旁路</button></div>
      {误 && <div className="提示条">升格被拒：{误}</div>}
      {!行.length ? (
        <div className="空态">暂无旁路。推完迟到修正后再推「超迟到旁路样例」或「旁路升格样例」。</div>
      ) : (
        <table>
          <thead>
            <tr><th>编号</th><th>原因</th><th>状态</th><th>载荷</th><th>时刻</th><th>操作</th></tr>
          </thead>
          <tbody>
            {行.map((r) => (
              <tr key={r.编号}>
                <td>{r.编号}</td><td>{r.原因}</td>
                <td><span className={`徽章 ${r.状态 === "已升格" ? "通" : ""}`}>{r.状态}</span></td>
                <td className="码">{r.载荷}</td><td className="码">{r.时刻}</td>
                <td>
                  {r.状态 === "未处理" && (
                    <button className="水" onClick={() => 升格(r.编号)}>升格</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div className="段">
        <div className="段题">升格回执（只读接口）</div>
        {!回执.length ? (
          <div className="空态">尚无升格。对未处理旁路点「升格」。</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>旁路编号</th><th>事件</th><th>原窗键</th><th>目标窗键</th>
                <th>原窗合计是否变</th><th>valid</th><th>升格时刻</th>
              </tr>
            </thead>
            <tbody>
              {回执.map((r) => (
                <tr key={r.回执编号}>
                  <td>{r.旁路编号}</td><td>{r.事件编号}</td>
                  <td className="码">{r.原窗键}</td><td className="码">{r.目标窗键}</td>
                  <td>{r.原窗合计是否变 ? "变" : "不变"}</td>
                  <td><span className={`徽章 ${r.valid ? "通" : "败"}`}>{r.valid ? "一致" : "分叉"}</span></td>
                  <td className="码">{r.升格时刻}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
