import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  ArrowUpRight,
  ArrowRight,
  RotateCcw,
  Play,
  Check,
  X,
  Download,
  BookOpen,
  Activity,
  CheckCheck,
  CircleDot,
  ChevronRight,
  AlertCircle,
} from "lucide-react";
import "@fontsource/dm-sans/400.css";
import "@fontsource/dm-sans/500.css";
import "@fontsource/dm-mono/400.css";
import "./style.css";
import { useInteractionFeedback } from "./interaction";
import HeroLab from "./HeroLab";

const names = {
  returns: "退換貨",
  fulfillment: "訂單出貨",
  changes: "地址變更",
};
const policyNames = {
  none: "無跨任務記憶",
  retrieval: "沿用既有記憶",
  ttl: "定期淘汰",
  refresh: "每次重新查證",
  selective: "選擇性更新",
};
const scheduleNames = {
  stable: "規則保持不變",
  single: "一次規則變更",
  multi: "多系統先後變更",
  recurring: "規則改變，再恢復",
};
const toolNames = {
  inspect_order: "查看訂單",
  read_policy: "查詢現行規則",
  inspect_stock: "查看庫存",
  refund_order: "辦理退款",
  fulfill_order: "出貨",
  change_order: "修改地址",
  finish: "結束任務",
};
const reasonNames = {
  too_old: "超過退貨期限",
  opened: "不接受已拆封品",
  max_quantity: "超過單筆數量上限",
  destination: "配送地區不符",
  out_of_stock: "庫存不足",
  locked: "已超過改單期限",
  service_level: "此配送類型不可改單",
  ok: "已完成",
};
const statusNames = {
  pending: "待處理",
  delivered: "已送達",
  refunded: "已退款",
  shipped: "已出貨",
};
const fmt = (n) => Number(n || 0).toLocaleString();

async function api(path, body) {
  const r = await fetch(
    `/api/${path}`,
    body !== undefined
      ? {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        }
      : {},
  );
  if (!r.ok) {
    const e = await r.json().catch(() => ({}));
    throw new Error(
      typeof e.detail === "string" ? e.detail : "服務暫時無法完成此操作",
    );
  }
  return r.json();
}

function PolicySheet({ rule, memory, scope }) {
  const remembered = memory?.policy;
  const old = remembered && rule && remembered.revision !== rule.revision;
  function body(p) {
    if (!p)
      return (
        <div className="empty-memory">
          <BookOpen size={24} />
          <p>還沒有觀察紀錄</p>
          <span>查詢一次規則，留下第一筆記憶。</span>
        </div>
      );
    if (scope === "returns")
      return (
        <>
          <div className="rule-number">
            {p.window_days}
            <small>天</small>
          </div>
          <p>購買後的退貨期限</p>
          <div className="rule-detail">
            已拆封商品 <b>{p.accept_opened ? "可接受" : "不接受"}</b>
          </div>
        </>
      );
    if (scope === "fulfillment")
      return (
        <>
          <div className="rule-number">
            {p.max_quantity}
            <small>件</small>
          </div>
          <p>單筆訂單數量上限</p>
          <div className="rule-detail">
            配送範圍{" "}
            <b>{p.destinations.includes("island") ? "本島與離島" : "僅本島"}</b>
          </div>
        </>
      );
    return (
      <>
        <div className="rule-number">
          {p.max_age_hours}
          <small>小時</small>
        </div>
        <p>訂單成立後可改地址</p>
        <div className="rule-detail">
          快遞訂單 <b>{p.allow_express ? "可更改" : "不可更改"}</b>
        </div>
      </>
    );
  }
  return (
    <div className="policy-pair">
      <article className="policy-sheet current">
        <div className="sheet-heading">
          <span className="dot orange" />
          此刻的世界 <span className="sheet-label">CURRENT</span>
        </div>
        {body(rule)}
        <div className="sheet-foot">研究者可見的現行規則</div>
      </article>
      <article className={`policy-sheet memory ${old ? "outdated" : ""}`}>
        <div className="sheet-heading">
          <span className={`dot ${old ? "red" : ""}`} />
          留下的記憶 <span className="sheet-label">MEMORY</span>
        </div>
        {body(remembered)}
        <div className="sheet-foot">
          {old ? (
            <>
              <AlertCircle size={13} /> 這筆記憶已不符合現行規則
            </>
          ) : remembered ? (
            <>
              <Check size={13} /> 與現行規則一致
            </>
          ) : (
            "僅顯示實際觀察過的證據"
          )}
        </div>
      </article>
    </div>
  );
}

function Order({ order, scope, request }) {
  if (!order) return null;
  return (
    <section className="order">
      <div className="section-line">
        <span>正在處理</span>
        <span className="mono">{order.id}</span>
      </div>
      <h3>{names[scope]}</h3>
      <p className="request">
        {request ||
          {
            returns: "依現行政策處理顧客退貨要求。",
            fulfillment: "在符合規則且庫存充足時出貨。",
            changes: "依顧客要求更改配送地址。",
          }[scope]}
      </p>
      <dl>
        <div>
          <dt>商品</dt>
          <dd>
            {order.sku === "notebook"
              ? "筆記本"
              : order.sku === "lamp"
                ? "桌燈"
                : "限量商品"}{" "}
            × {order.quantity}
          </dd>
        </div>
        <div>
          <dt>{scope === "returns" ? "購買天數" : "訂單時間"}</dt>
          <dd>
            {scope === "returns"
              ? `${order.age_days} 天`
              : `${order.age_hours} 小時前`}
          </dd>
        </div>
        <div>
          <dt>{scope === "returns" ? "商品狀況" : "配送方式"}</dt>
          <dd>
            {scope === "returns"
              ? order.opened
                ? "已拆封"
                : "未拆封"
              : `${order.service === "express" ? "快遞" : "標準"} · ${order.destination === "island" ? "離島" : "本島"}`}
          </dd>
        </div>
        <div>
          <dt>狀態</dt>
          <dd>
            <span className="status">
              {statusNames[order.status] || order.status}
            </span>
          </dd>
        </div>
      </dl>
    </section>
  );
}

function Timeline({
  selected,
  onSelect,
  available = 8,
  schedule,
  live = false,
}) {
  return (
    <div className="timeline-wrap">
      <div className="section-line">
        <span>世界的時間線</span>
        <span className="mono">
          {String(selected + 1).padStart(2, "0")} / 08
        </span>
      </div>
      <div className="timeline" aria-label="選擇任務">
        <div className="rail" />
        <div
          className="rail-fill"
          style={{ width: `${(selected / 7) * 100}%` }}
        />
        {Array.from({ length: 8 }, (_, i) => {
          const change =
            (schedule !== "stable" && i === 3) ||
            (schedule === "multi" && i === 5) ||
            (schedule === "recurring" && i === 6);
          return (
            <button
              key={i}
              className={`time-point ${i === selected ? "selected" : ""} ${change ? "change" : ""}`}
              disabled={i >= available || (live && i !== selected)}
              onClick={() => onSelect(i)}
              aria-label={`任務 ${i + 1}${change ? "，規則變更" : ""}，${names[["returns", "fulfillment", "changes", "returns", "fulfillment", "changes", "returns", "returns"][i]]}，${change ? (schedule === "recurring" && i === 6 ? "恢復原始規則" : "此處改變規則") : "延續當前規則"}`}
              aria-pressed={i === selected}
              aria-describedby={`timeline-hint-${i}`}
            >
              <span
                className="timeline-hint"
                role="tooltip"
                id={`timeline-hint-${i}`}
              >
                {
                  names[
                    [
                      "returns",
                      "fulfillment",
                      "changes",
                      "returns",
                      "fulfillment",
                      "changes",
                      "returns",
                      "returns",
                    ][i]
                  ]
                }{" "}
                ·{" "}
                {change
                  ? schedule === "recurring" && i === 6
                    ? "恢復原始規則"
                    : "此處改變規則"
                  : "延續當前規則"}
              </span>
              <span className="time-circle">
                {i === selected ? (
                  <CircleDot size={17} />
                ) : (
                  String(i + 1).padStart(2, "0")
                )}
              </span>
              <span className="time-label">
                {change ? "規則變更" : `任務 ${i + 1}`}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function History({ history }) {
  return (
    <section className="history">
      <div className="section-line">
        <span>實際發生了什麼</span>
        <span className="mono">{history.length} EVENTS</span>
      </div>
      {history.length === 0 ? (
        <p className="quiet">世界正在等待第一個動作。</p>
      ) : (
        <ol>
          {history.map((h, i) => {
            let action =
              typeof h.action === "object"
                ? h.action
                : { tool: "invalid_action" };
            const result = h.result || h.observation?.result || {};
            return (
              <li key={i}>
                <span
                  className={`event-mark ${result.error ? "bad" : result.applied ? "good" : ""}`}
                >
                  {result.error ? (
                    <X size={12} />
                  ) : result.applied ? (
                    <Check size={12} />
                  ) : (
                    <ChevronRight size={12} />
                  )}
                </span>
                <details>
                  <summary>
                    <span>
                      {toolNames[action.tool] || "無法解析的模型輸出"}
                    </span>
                    <small>
                      {result.reason
                        ? reasonNames[result.reason] || result.reason
                        : result.error
                          ? "操作未通過"
                          : result.applied
                            ? "已改變世界狀態"
                            : result.task_closed
                              ? "任務已結束"
                              : result.policy
                                ? "規則已讀取"
                                : "取得觀察結果"}
                    </small>
                    {h.origin === "memory_policy" && <em>記憶策略查證</em>}
                  </summary>
                  <pre>
                    {JSON.stringify({ action: h.action, result }, null, 2)}
                  </pre>
                </details>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}

function App() {
  const [tab, setTab] = useState("home"),
    [world, setWorld] = useState(null),
    [sid, setSid] = useState(null),
    [schedule, setSchedule] = useState("recurring");
  const [memory, setMemory] = useState({}),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [online, setOnline] = useState(false);
  const [datasets, setDatasets] = useState([]),
    [data, setData] = useState(null),
    [dataset, setDataset] = useState(""),
    [policy, setPolicy] = useState("selective"),
    [replaySchedule, setReplaySchedule] = useState("recurring"),
    [seed, setSeed] = useState(null),
    [episode, setEpisode] = useState(0);
  const [reason, setReason] = useState("too_old");
  useInteractionFeedback(tab);
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "instant" });
  }, [tab]);
  useEffect(() => {
    api("health")
      .then(() => {
        setOnline(true);
        return refreshDatasets();
      })
      .catch(loadBundledDataset);
  }, []);
  async function loadBundledDataset() {
    try {
      const response = await fetch("./explorer.json");
      if (!response.ok) throw Error();
      const d = await response.json();
      setData(d);
      setDataset("");
      setSeed(d.manifest.config.seeds[0]);
      setReplaySchedule(d.manifest.config.schedules.at(-1));
      setPolicy(
        d.manifest.config.policies.includes("selective")
          ? "selective"
          : d.manifest.config.policies[0],
      );
      setEpisode(0);
    } catch {
      setNotice("啟動本機服務後，即可操作世界與查看實驗。");
    }
  }
  async function refreshDatasets() {
    const ds = await api("experiments");
    setDatasets(ds);
    const preferred =
      [...ds].reverse().find((d) => d.available && d.split === "test") ||
      [...ds].reverse().find((d) => d.available && d.name !== "smoke-v1");
    if (preferred) await loadDataset(preferred.name);
    else await loadBundledDataset();
  }
  async function loadDataset(name) {
    try {
      const d = await api(`experiments/${name}`);
      setData(d);
      setDataset(name);
      setSeed(d.manifest.config.seeds[0]);
      setReplaySchedule(d.manifest.config.schedules.at(-1));
      setPolicy(
        d.manifest.config.policies.includes("selective")
          ? "selective"
          : d.manifest.config.policies[0],
      );
      setEpisode(0);
    } catch (e) {
      setError(e.message);
    }
  }
  async function task(fn) {
    if (busy) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await fn();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function create() {
    await task(async () => {
      const r = await api("world", { seed: 17, schedule });
      setSid(r.session_id);
      setWorld(r);
      setTab("world");
      setMemory({});
      setNotice("新的世界已開始。先查看訂單與規則，再決定如何處理。");
    });
  }
  async function action(tool, args) {
    await task(async () => {
      const r = await api(`world/${sid}/action`, { tool, args });
      setWorld(r);
      const last = r.events.at(-1)?.observation?.result;
      if (last?.policy)
        setMemory((m) => ({
          ...m,
          [last.policy.scope]: { policy: last.policy },
        }));
      if (last?.reason) setReason(last.reason);
    });
  }
  async function next() {
    await task(async () => {
      const r = await api(`world/${sid}/next`, {});
      setWorld(r);
      const change = r.events.at(-1)?.changed_scopes;
      setNotice(
        change?.length
          ? "世界規則已改變；已保存的觀察不會自動更新。"
          : "進入下一個任務，先前操作造成的狀態仍保留。",
      );
    });
  }
  const live = world?.world,
    scope = live?.task?.scope,
    order = live?.orders?.[live?.task?.order_id];
  const records =
    data?.records.filter(
      (r) =>
        r.policy === policy &&
        r.schedule === replaySchedule &&
        r.seed === Number(seed),
    ) || [];
  const record = records.find((r) => r.task_index === episode) || records[0];
  const history =
    world?.events
      .filter((e) => e.kind === "tool" && e.index === live?.task_index)
      .map((e) => ({ action: e.action, result: e.observation.result })) || [];
  const download = async () => {
    await task(async () => {
      const snapshot = await api(`world/${sid}/snapshot`);
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(snapshot, null, 2)], {
          type: "application/json",
        }),
      );
      const a = document.createElement("a");
      a.href = url;
      a.download = "ruleshift-world.json";
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
  };
  return (
    <>
      <a className="skip" href="#main">
        跳至主要內容
      </a>
      <header>
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            setTab("home");
            setNotice("");
            setError("");
          }}
        >
          <span className="brand-mark">↗</span>
          <b>RuleShift</b>
        </a>
        <nav className="header-nav" aria-label="主要導覽">
          {[
            ["home", "概覽"],
            ["world", "互動世界"],
            ["replay", "模型實驗"],
            ["method", "研究方法"],
          ].map(([key, label]) => (
            <button
              key={key}
              aria-current={tab === key ? "page" : undefined}
              onClick={() => {
                setTab(key);
                setNotice("");
                setError("");
                if (key === "replay" && online && !data)
                  refreshDatasets().catch(() => {});
              }}
            >
              {label}
            </button>
          ))}
        </nav>
        <a
          href="https://github.com/Chih-Kai-Wang/ruleshift"
          target="_blank"
          rel="noreferrer"
          className="source-link"
        >
          GitHub <ArrowUpRight size={15} />
        </a>
      </header>
      <main id="main" className={tab === "home" ? "home" : "workspace-open"}>
        {tab === "home" && (
          <>
            <HeroLab
              online={online}
              busy={busy}
              onEnter={create}
              onReplay={() => setTab("replay")}
            />
            <section className="home-explainer">
              <h2>
                記住答案，
                <br />
                不等於理解現在。
              </h2>
              <div>
                <p>
                  Agent
                  必須處理退貨、出貨與改單。當有效期限、配送範圍或操作條件改變，昨天的經驗就可能導向今天的錯誤。
                </p>
                <p>
                  RuleShift
                  把這個問題拆開來看：它讀了什麼、做了什麼、世界真的改變了什麼，以及為了正確完成任務付出了多少成本。
                </p>
                <button className="text-link" onClick={() => setTab("method")}>
                  看看我們怎麼驗證 <ArrowRight size={16} />
                </button>
              </div>
            </section>
            <section className="home-evidence">
              <span className="eyebrow">讓結果說話</span>
              <h2>
                同一個世界。
                <br />
                五種記憶策略。
              </h2>
              <p>
                從完全不保留記憶，到每次重新查證。比較實際結果，也把失敗留在畫面裡。
              </p>
              {data && (
                <div
                  className="strategy-chart"
                  aria-label="實測策略成功率，點選查看回放"
                >
                  <div className="strategy-chart-heading">
                    <span>實測成功率</span>
                    <span>
                      點選策略，追蹤每一步 <ArrowRight size={13} />
                    </span>
                  </div>
                  {data.summary.policies.map((row) => (
                    <button
                      key={row.policy}
                      className="strategy-row"
                      onClick={() => {
                        setPolicy(row.policy);
                        setEpisode(0);
                        setTab("replay");
                      }}
                      aria-label={`${policyNames[row.policy]}，成功 ${row.successes} / ${row.n}，查看回放`}
                    >
                      <span className="strategy-name">
                        {policyNames[row.policy]}
                      </span>
                      <span className="strategy-track" aria-hidden="true">
                        <span style={{ width: `${row.success_rate * 100}%` }} />
                      </span>
                      <span className="strategy-rate">
                        {(row.success_rate * 100).toFixed(1)}
                        <small>%</small>
                      </span>
                      <span className="strategy-detail">
                        {row.successes} / {row.n} 成功 · {fmt(row.policy_reads)}{" "}
                        次查詢嘗試
                      </span>
                      <ArrowUpRight className="strategy-arrow" size={17} />
                    </button>
                  ))}
                </div>
              )}
              <button onClick={() => setTab("replay")}>
                查看逐步回放 <ArrowRight size={16} />
              </button>
              {data && (
                <small>
                  {data.summary.completed_tasks} / {data.summary.planned_tasks}{" "}
                  次任務 · {data.manifest.config.split.toUpperCase()} ·{" "}
                  {data.summary.complete ? "此批次已完成" : "此批次仍在進行"}
                </small>
              )}
            </section>
          </>
        )}
        {tab !== "home" && (
          <div className="workspace-heading">
            <div>
              <span className="eyebrow">RULESHIFT</span>
              <h1>
                {tab === "world"
                  ? "親手操作這個世界"
                  : tab === "replay"
                    ? "模型如何面對改變"
                    : "每個結論，都能追查"}
              </h1>
            </div>
            <span className="local-state">
              <span className={`dot ${online ? "green" : ""}`} />
              {online ? "本機世界在線" : "公開研究回放"}
            </span>
          </div>
        )}
        <div className="announcements" aria-live="polite">
          {error && (
            <div className="error">
              <AlertCircle size={15} />
              {error}
            </div>
          )}
          {notice && <div className="notice">{notice}</div>}
        </div>
        {tab === "world" && (
          <>
            <div className="toolbar">
              <div>
                <label htmlFor="schedule">世界規則如何變動</label>
                <select
                  id="schedule"
                  value={schedule}
                  onChange={(e) => setSchedule(e.target.value)}
                  disabled={busy}
                >
                  {Object.entries(scheduleNames).map(([k, v]) => (
                    <option value={k} key={k}>
                      {v}
                    </option>
                  ))}
                </select>
              </div>
              <button
                className="primary"
                disabled={busy || !online}
                onClick={create}
              >
                {world ? <RotateCcw size={15} /> : <Play size={15} />}{" "}
                {world ? "開始新的世界" : "進入世界"} <ArrowRight size={16} />
              </button>
            </div>
            {!world ? (
              <section className="world-intro">
                <h2>先觀察，再行動。</h2>
                <p>
                  選擇規則變化方式，開始八個連續任務。
                  <br />
                  你的操作會改變訂單與庫存，時間推進後，記憶則不會自動更新。
                </p>
                {!online && (
                  <p>互動世界需要本機服務。你仍可以查看完整的模型實驗回放。</p>
                )}
                <p className="fineprint">
                  這是研究者操作介面；參考解法使用環境真值，並非模型表現。
                </p>
              </section>
            ) : (
              <>
                <Timeline
                  selected={live.task_index}
                  schedule={live.schedule}
                  live
                />
                <div className="workbench">
                  <div className="world-column">
                    <div className="section-line">
                      <span>{names[scope]} / 規則與記憶</span>
                      <span className="mono">RESEARCHER VIEW</span>
                    </div>
                    <PolicySheet
                      rule={live.rules[scope]}
                      memory={memory[scope]}
                      scope={scope}
                    />
                    <div className="action-row">
                      <button
                        disabled={busy || live.done}
                        onClick={() => action("read_policy", { scope })}
                      >
                        <BookOpen size={15} />
                        查詢並記住規則
                      </button>
                      <button
                        disabled={busy || live.done}
                        onClick={() =>
                          action("inspect_order", { order_id: order.id })
                        }
                      >
                        查看訂單紀錄 <ArrowUpRight size={14} />
                      </button>
                    </div>
                    <History history={history} />
                  </div>
                  <aside>
                    <Order order={order} scope={scope} request={null} />
                    <div className="control-panel">
                      <span className="control-title">你會如何處理？</span>
                      <button
                        className="primary wide"
                        disabled={busy || live.done}
                        onClick={() =>
                          action(
                            {
                              returns: "refund_order",
                              fulfillment: "fulfill_order",
                              changes: "change_order",
                            }[scope],
                            {
                              order_id: order.id,
                              ...(scope === "changes"
                                ? { address: live.task.requested_address }
                                : {}),
                            },
                          )
                        }
                      >
                        嘗試
                        {scope === "returns"
                          ? "退款"
                          : scope === "fulfillment"
                            ? "出貨"
                            : "更改地址"}{" "}
                        <ArrowRight size={15} />
                      </button>
                      <div className="deny-row">
                        <select
                          aria-label="拒絕原因"
                          value={reason}
                          onChange={(e) => setReason(e.target.value)}
                          disabled={busy || live.done}
                        >
                          {Object.entries(reasonNames)
                            .filter(([k]) => k !== "ok")
                            .map(([k, v]) => (
                              <option key={k} value={k}>
                                {v}
                              </option>
                            ))}
                        </select>
                        <button
                          disabled={busy || live.done}
                          onClick={() =>
                            action("finish", { decision: "deny", reason })
                          }
                        >
                          拒絕
                        </button>
                      </div>
                      <button
                        className="wide"
                        disabled={busy || live.done}
                        onClick={() =>
                          action("finish", {
                            decision: "complete",
                            reason: "ok",
                          })
                        }
                      >
                        <Check size={15} />
                        確認已完成
                      </button>
                      <button
                        className="text-button"
                        disabled={busy || live.done}
                        onClick={() =>
                          task(async () => {
                            setWorld(await api(`world/${sid}/reference`, {}));
                            setNotice(
                              "已執行特權參考解法：用於驗證環境，不能當作 AI 成績。",
                            );
                          })
                        }
                      >
                        使用參考解法（非模型）
                      </button>
                      {world.score && (
                        <div
                          className={`outcome ${world.score.success ? "pass" : "fail"}`}
                        >
                          {world.score.success ? (
                            <CheckCheck size={18} />
                          ) : (
                            <X size={18} />
                          )}
                          <div>
                            <b>
                              {world.score.success
                                ? "任務結果正確"
                                : "任務未正確完成"}
                            </b>
                            <small>
                              {world.score.state_ok
                                ? "世界狀態符合要求"
                                : "世界狀態不符合要求"}{" "}
                              ·{" "}
                              {world.score.decision_ok
                                ? "結論正確"
                                : "結論不符"}
                            </small>
                          </div>
                        </div>
                      )}
                      <button
                        className="next wide"
                        disabled={busy || !live.done || live.task_index >= 7}
                        onClick={next}
                      >
                        {live.task_index >= 7
                          ? "八個任務已結束"
                          : "時間往前，下一個任務"}
                        <ArrowRight size={16} />
                      </button>
                      <div className="budget">
                        已使用 {live.calls} / {live.tool_budget} 次工具呼叫
                      </div>
                    </div>
                  </aside>
                </div>
                <div className="evidence-strip">
                  <span>
                    <Activity size={15} /> 每次狀態轉移均有可驗證紀錄
                  </span>
                  <button
                    disabled={busy}
                    onClick={() =>
                      task(async () => {
                        const r = await api(`world/${sid}/replay`);
                        setNotice(
                          `重播驗證通過：${r.events} 個事件，重建出完全相同的世界。`,
                        );
                      })
                    }
                  >
                    驗證重播 <CheckCheck size={14} />
                  </button>
                  <button disabled={busy} onClick={download}>
                    下載世界快照 <Download size={14} />
                  </button>
                </div>
              </>
            )}
          </>
        )}
        {tab === "replay" && (
          <>
            {!data ? (
              <div className="no-data">
                <Activity size={32} />
                <h2>實驗正在累積證據。</h2>
                <p>完成的真模型軌跡會在這裡提供逐步回放。</p>
                {datasets.map((d) => (
                  <p className="mono" key={d.name}>
                    {d.name} · {d.completed} / {d.planned}
                  </p>
                ))}
                {online && (
                  <button
                    onClick={() =>
                      refreshDatasets().catch((e) => setError(e.message))
                    }
                  >
                    重新整理
                  </button>
                )}
              </div>
            ) : (
              <>
                <div className="results-heading">
                  <div className="eyebrow">OBSERVED, NOT SCRIPTED</div>
                  <h2>
                    同一個世界，<i>不同的記憶。</i>
                  </h2>
                  <p>
                    以下是本機模型實際呼叫工具的紀錄。
                    {data.summary.complete
                      ? "此批次已全部完成。"
                      : "此批次尚未完成，數字為暫時結果。"}
                  </p>
                  <span className="model-label">
                    {data.manifest.config.model} ·{" "}
                    {data.manifest.config.split.toUpperCase()} ·{" "}
                    {data.summary.completed_tasks} /{" "}
                    {data.summary.planned_tasks} 任務
                  </span>
                </div>
                <div className="filters">
                  {online && datasets.some((d) => d.available) && (
                    <label>
                      實驗批次
                      <select
                        value={dataset}
                        onChange={(e) => loadDataset(e.target.value)}
                      >
                        {datasets
                          .filter((d) => d.available && d.name !== "smoke-v1")
                          .map((d) => (
                            <option key={d.name}>{d.name}</option>
                          ))}
                      </select>
                    </label>
                  )}
                  <label>
                    記憶策略
                    <select
                      value={policy}
                      onChange={(e) => {
                        setPolicy(e.target.value);
                        setEpisode(0);
                      }}
                    >
                      {data.manifest.config.policies.map((p) => (
                        <option key={p} value={p}>
                          {policyNames[p]}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    規則變化
                    <select
                      value={replaySchedule}
                      onChange={(e) => {
                        setReplaySchedule(e.target.value);
                        setEpisode(0);
                      }}
                    >
                      {data.manifest.config.schedules.map((s) => (
                        <option key={s} value={s}>
                          {scheduleNames[s]}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    世界種子
                    <select
                      value={seed ?? ""}
                      onChange={(e) => {
                        setSeed(Number(e.target.value));
                        setEpisode(0);
                      }}
                    >
                      {data.manifest.config.seeds.map((s) => (
                        <option key={s}>{s}</option>
                      ))}
                    </select>
                  </label>
                </div>
                {!record && (
                  <p className="notice">
                    此組合尚未產生任務紀錄。請選擇已完成的世界或稍後重新整理。
                  </p>
                )}
                {record && (
                  <>
                    <Timeline
                      selected={record.task_index}
                      onSelect={setEpisode}
                      available={records.length}
                      schedule={replaySchedule}
                    />
                    <div className="workbench">
                      <div className="world-column">
                        <PolicySheet
                          rule={record.rules[record.score.scope]}
                          memory={record.memory_at_start[0]}
                          scope={record.score.scope}
                        />
                        <div className="replay-note">
                          記憶欄顯示本任務開始時的觀察；任務中的查證與更新請展開下方紀錄。
                        </div>
                        <History history={record.history} />
                      </div>
                      <aside>
                        <Order
                          order={record.order}
                          scope={record.score.scope}
                        />
                        <div className="observed-transition">
                          <span>
                            實際訂單變化 ·{" "}
                            {record.score.scope === "changes" ? "地址" : "狀態"}
                          </span>
                          <div>
                            <span>
                              {record.score.scope === "changes"
                                ? record.order.address
                                : statusNames[record.order.status] ||
                                  record.order.status}
                            </span>
                            <ArrowRight size={15} aria-hidden="true" />
                            <b>
                              {record.score.scope === "changes"
                                ? record.after.address
                                : statusNames[record.after.status] ||
                                  record.after.status}
                            </b>
                          </div>
                        </div>
                        <div
                          className={`outcome ${record.score.success ? "pass" : "fail"}`}
                        >
                          {record.score.success ? <CheckCheck /> : <X />}
                          <div>
                            <b>
                              {record.score.success ? "任務成功" : "任務失敗"}
                            </b>
                            <small>
                              {record.score.state_ok
                                ? "實際狀態正確"
                                : "實際狀態錯誤"}{" "}
                              ·{" "}
                              {record.score.decision_ok
                                ? "結論正確"
                                : "結論錯誤"}
                            </small>
                          </div>
                        </div>
                        <div className="costs">
                          <div>
                            <span>工具呼叫</span>
                            <b>{record.cost.tool_calls}</b>
                          </div>
                          <div>
                            <span>規則查詢嘗試</span>
                            <b>{record.cost.policy_reads}</b>
                          </div>
                          <div>
                            <span>輸入 / 輸出 tokens</span>
                            <b>
                              {fmt(record.cost.prompt_tokens)} /{" "}
                              {fmt(record.cost.completion_tokens)}
                            </b>
                          </div>
                          <div>
                            <span>本機模型時間</span>
                            <b>{record.cost.model_seconds.toFixed(1)} s</b>
                          </div>
                        </div>
                        <p className="fineprint">
                          所有失敗保留在分母。查詢嘗試包含無效參數；本輪有明顯的參數格式與重複操作失敗，不能單憑成功率推論記憶策略優劣。
                        </p>
                      </aside>
                    </div>
                  </>
                )}
                <section className="summary">
                  <div className="section-line">
                    <span>完整批次比較</span>
                    <span className="mono">
                      {data.summary.completed_tasks} OBSERVED TASKS
                    </span>
                  </div>
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>記憶策略</th>
                          <th>成功 / 任務數</th>
                          <th>成功率</th>
                          <th>工具呼叫</th>
                          <th>查詢嘗試</th>
                          <th>總 tokens</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.summary.policies.map((p) => (
                          <tr
                            key={p.policy}
                            className={p.policy === policy ? "highlight" : ""}
                          >
                            <td>{policyNames[p.policy]}</td>
                            <td>
                              {p.successes} / {p.n}
                            </td>
                            <td>{(p.success_rate * 100).toFixed(1)}%</td>
                            <td>{fmt(p.tool_calls)}</td>
                            <td>{fmt(p.policy_reads)}</td>
                            <td>
                              {fmt(p.prompt_tokens + p.completion_tokens)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {data.summary.paired_comparison && (
                    <p className="fineprint">
                      選擇性更新 − 每次查證：
                      {(
                        data.summary.paired_comparison.mean_success_difference *
                        100
                      ).toFixed(1)}{" "}
                      個百分點；95% 配對任務串 bootstrap 區間 [
                      {data.summary.paired_comparison.bootstrap_95_percent_interval
                        .map((n) => (n * 100).toFixed(1))
                        .join(", ")}
                      ]。統計單位為 {data.summary.paired_comparison.n_pairs}{" "}
                      條配對任務串；相同五個種子跨情境重用，獨立性與樣本量有限，請同時參閱{" "}
                      <a
                        href="https://github.com/Chih-Kai-Wang/ruleshift/blob/main/docs/RESULTS.md"
                        target="_blank"
                        rel="noreferrer"
                      >
                        種子分組敏感度分析與失敗原因
                      </a>
                      。
                    </p>
                  )}
                </section>
              </>
            )}
          </>
        )}
        {tab === "method" && (
          <section className="methods">
            <div className="eyebrow">
              A SMALL WORLD. AN INSPECTABLE EXPERIMENT.
            </div>
            <h2>
              讓結論，<i>跟著證據走。</i>
            </h2>
            <div className="method-grid">
              <article>
                <span>01 / WORLD</span>
                <h3>狀態會留下來</h3>
                <p>
                  出貨消耗庫存，退款留下紀錄，更改地址影響訂單。規則按固定種子與模擬時間改變，完整動作序列可以重播。
                </p>
              </article>
              <article>
                <span>02 / OBSERVATION</span>
                <h3>模型不會看到答案</h3>
                <p>
                  模型只能看到任務、工具與已取得的觀察。本頁的研究者規則視圖、隱藏答案與未來排程不會送入模型。
                </p>
              </article>
              <article>
                <span>03 / COMPARISON</span>
                <h3>簡單方法也是強對手</h3>
                <p>
                  比較無記憶、既有記憶、定期淘汰、每次查證與選擇性更新。所有額外查詢與模型輸入、輸出
                  token
                  成本都計入。各策略共用的三筆初始規則觀察屬於暖身設定，不列入任務內查詢成本。
                </p>
              </article>
              <article>
                <span>04 / EVIDENCE</span>
                <h3>失敗也是研究結果</h3>
                <p>
                  評分器檢查實際訂單與庫存。沒有完成操作的「成功」不會被接受；不預設新策略必須勝出。
                </p>
              </article>
            </div>
            <div className="method-foot">
              <h3>我們實際研究的是什麼？</h3>
              <p>
                固定模型權重下，記憶與行動策略如何面對規則改變。這個小型、合成、單模型實驗，不宣稱證明模型參數持續學習，也不推論到生產環境。
              </p>
              <div className="method-links">
                <a
                  href="https://github.com/Chih-Kai-Wang/ruleshift/blob/main/docs/PROTOCOL.md"
                  target="_blank"
                  rel="noreferrer"
                >
                  閱讀實驗協議 <ArrowUpRight size={15} />
                </a>
                <a
                  href="https://github.com/Chih-Kai-Wang/ruleshift/releases"
                  target="_blank"
                  rel="noreferrer"
                >
                  原始紀錄與版本 <ArrowUpRight size={15} />
                </a>
              </div>
            </div>
          </section>
        )}
        <footer>
          <span className="footer-mark">↗</span>
          <div>
            RuleShift <small>A world that changes its mind.</small>
          </div>
          <span>本機優先 / 開源 / 可重現</span>
        </footer>
      </main>
    </>
  );
}

createRoot(document.getElementById("root")).render(<App />);
