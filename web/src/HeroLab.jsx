import React, { useRef, useState, useEffect } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  Grip,
  RotateCcw,
  Check,
  X,
  ScanLine,
  MoveRight,
  Play,
  Package,
  CheckCheck,
} from "lucide-react";
import "./lab.css";

const scenarios = {
  returns: {
    name: "退貨",
    a: 30,
    b: 14,
    unit: "天",
    rule: "退貨期限",
    amount: 20,
    item: "購買 20 天的未拆封商品",
    action: "接受退貨",
    deny: "拒絕退貨",
  },
  fulfillment: {
    name: "出貨",
    a: 6,
    b: 3,
    unit: "件",
    rule: "每單出貨上限",
    amount: 4,
    item: "一筆 4 件商品的本島訂單",
    action: "安排出貨",
    deny: "拒絕出貨",
  },
  changes: {
    name: "改單",
    a: 72,
    b: 18,
    unit: "小時",
    rule: "可修改地址的時間",
    amount: 24,
    item: "成立 24 小時的標準配送訂單",
    action: "修改地址",
    deny: "拒絕改單",
  },
};

export default function HeroLab({ onEnter, onReplay, online, busy }) {
  const [kind, setKind] = useState("returns");
  const [time, setTime] = useState(50);
  const [remembered, setRemembered] = useState(30);
  const [reads, setReads] = useState(0);
  const [result, setResult] = useState(null);
  const [scanning, setScanning] = useState(false);
  const [drag, setDrag] = useState(null);
  const [over, setOver] = useState(false);
  const target = useRef(null),
    moved = useRef(false),
    start = useRef(null),
    timer = useRef(null);
  const spec = scenarios[kind],
    phase = time < 34 ? 0 : time < 75 ? 1 : 2;
  const current = phase === 1 ? spec.b : spec.a,
    stale = remembered !== current;
  useEffect(() => () => clearTimeout(timer.current), []);
  function reset(next = kind) {
    clearTimeout(timer.current);
    start.current = null;
    moved.current = false;
    setKind(next);
    setTime(50);
    setRemembered(scenarios[next].a);
    setReads(0);
    setResult(null);
    setScanning(false);
    setDrag(null);
    setOver(false);
  }
  function sync() {
    if (scanning) return;
    setScanning(true);
    setResult(null);
    const value = current;
    timer.current = setTimeout(
      () => {
        setRemembered(value);
        setReads((n) => n + 1);
        setScanning(false);
      },
      matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 620,
    );
  }
  function pointerDown(e) {
    if (e.button !== 0 || scanning) return;
    moved.current = false;
    start.current = { x: e.clientX, y: e.clientY };
    e.currentTarget.setPointerCapture(e.pointerId);
  }
  function pointerMove(e) {
    if (!start.current) return;
    if (
      Math.hypot(e.clientX - start.current.x, e.clientY - start.current.y) <
        7 &&
      !moved.current
    )
      return;
    moved.current = true;
    setDrag({ x: e.clientX, y: e.clientY });
    const box = target.current.getBoundingClientRect();
    setOver(
      e.clientX >= box.left &&
        e.clientX <= box.right &&
        e.clientY >= box.top &&
        e.clientY <= box.bottom,
    );
  }
  function pointerEnd(e) {
    if (!start.current) return;
    const box = target.current.getBoundingClientRect();
    if (
      moved.current &&
      e.clientX >= box.left &&
      e.clientX <= box.right &&
      e.clientY >= box.top &&
      e.clientY <= box.bottom
    )
      sync();
    start.current = null;
    setDrag(null);
    setOver(false);
  }
  function act() {
    const decision = spec.amount <= remembered,
      allowed = spec.amount <= current;
    setResult({ decision, allowed, correct: decision === allowed });
  }
  return (
    <>
      <section className="lab-intro">
        <div>
          <div className="lab-kicker">
            <span /> A SMALL WORLD. A REAL QUESTION.
          </div>
          <h1 className="interactive-title">
            <i className="title-lens" aria-hidden="true" />
            規則變了。
            <br />
            <span>記憶呢？</span>
          </h1>
        </div>
        <div className="lab-intro-side">
          <p>
            昨天的正確答案，
            <br />
            可能是今天的錯誤。
            <br />
            <span>親手改變世界，看看 Agent 的記憶能否跟上。</span>
          </p>
          <div className="hero-actions">
            <button
              className="primary"
              disabled={busy}
              onClick={online ? onEnter : onReplay}
            >
              {online ? "進入完整世界" : "探索模型實驗"}
              <ArrowUpRight size={16} />
            </button>
            <button className="lab-replay-link" onClick={onReplay}>
              研究紀錄 <ArrowRight size={16} />
            </button>
          </div>
        </div>
      </section>
      <section
        className={`hero-lab ${stale ? "is-stale" : "is-current"} ${scanning ? "is-scanning" : ""} ${drag ? "is-dragging" : ""}`}
        aria-label="可拖曳的規則與記憶實驗室"
      >
        <div className="lab-topline">
          <div
            className="lab-scenario"
            aria-label="互動示意情境"
            style={{ "--choice": Object.keys(scenarios).indexOf(kind) }}
          >
            <span className="lab-choice-pill" aria-hidden="true" />
            {Object.entries(scenarios).map(([k, s]) => (
              <button
                key={k}
                aria-pressed={kind === k}
                onClick={() => reset(k)}
              >
                {s.name}
              </button>
            ))}
          </div>
          <span className="lab-mode">
            <span /> LIVE PLAYGROUND <b>互動示意 · 非模型結果</b>
          </span>
          <button
            className="lab-reset"
            aria-label="重設互動示意"
            onClick={() => reset()}
          >
            <RotateCcw size={15} />
          </button>
        </div>
        <div className="lab-stage">
          <div className="stage-grid" aria-hidden="true" />
          <svg
            className="signal-path"
            viewBox="0 0 1000 360"
            preserveAspectRatio="none"
            aria-hidden="true"
          >
            <path
              className="signal-track"
              d="M 265 205 C 390 205, 400 75, 500 75 S 610 205, 735 205"
            />
            <path
              className="signal-flow"
              d="M 265 205 C 390 205, 400 75, 500 75 S 610 205, 735 205"
            />
          </svg>
          <div className="stage-annotation">
            <span className="annotation-line" />
            <span>
              {scanning
                ? "正在傳遞新的觀察"
                : stale
                  ? "世界向前走了，記憶還停在原地"
                  : "這一刻，記憶與世界一致"}
            </span>
          </div>
          <article className="rule-object world-object">
            <div className="object-top">
              <span className="object-dot" />
              <span>世界現在</span>
              <span className="object-code">WORLD</span>
            </div>
            <div className="object-value" key={`${kind}-${current}`}>
              {current}
              <span>{spec.unit}</span>
            </div>
            <p className="object-rule">{spec.rule}</p>
            <div className="object-stamp">
              {phase === 0
                ? "原始規則"
                : phase === 1
                  ? "現行規則已變更"
                  : "原始規則已恢復"}
              <span>{phase === 1 ? "B" : "A"}</span>
            </div>
            <button
              className="transfer-ticket"
              disabled={scanning}
              onPointerDown={pointerDown}
              onPointerMove={pointerMove}
              onPointerUp={pointerEnd}
              onPointerCancel={() => {
                start.current = null;
                setDrag(null);
                setOver(false);
              }}
              onClick={(e) => {
                if (e.detail === 0 || !moved.current) sync();
              }}
              aria-label="拖曳到記憶區，或點擊以查證更新"
            >
              <Grip size={16} />
              <span>{scanning ? "讀取規則中…" : "拖曳這份規則"}</span>
              <MoveRight size={17} />
            </button>
          </article>
          <div className="stage-middle" aria-hidden="true">
            <div className={`state-orbit ${stale ? "split" : ""}`}>
              <span />
              <span />
              <i>
                {scanning ? (
                  <ScanLine size={25} />
                ) : stale ? (
                  <span className="orbit-gap">≠</span>
                ) : (
                  <Check size={25} />
                )}
              </i>
            </div>
            <p>{scanning ? "同步觀察" : stale ? "尚未同步" : "同步完成"}</p>
          </div>
          <article
            ref={target}
            className={`rule-object memory-object ${over ? "drop-ready" : ""}`}
          >
            <div className="object-top">
              <span className="object-dot" />
              <span>Agent 記得</span>
              <span className="object-code">MEMORY</span>
            </div>
            <div className="object-value" key={`${kind}-memory-${remembered}`}>
              {remembered}
              <span>{spec.unit}</span>
            </div>
            <p className="object-rule">{spec.rule}</p>
            <div className={`memory-badge ${stale ? "outdated" : ""}`}>
              {scanning ? (
                <>
                  <ScanLine size={13} /> 查證中
                </>
              ) : stale ? (
                <>
                  <span className="badge-dot" /> 記憶已經過期
                </>
              ) : (
                <>
                  <CheckCheck size={14} /> 與現行規則一致
                </>
              )}
            </div>
            <div className="drop-hint">
              {over
                ? "鬆開，讓記憶跟上世界"
                : stale
                  ? "← 把左邊的規則拖到這裡"
                  : "已取得現行規則"}
            </div>
            <div className="scan-sweep" aria-hidden="true" />
          </article>
        </div>
        {drag && (
          <div
            className={`drag-ticket ${over ? "ready" : ""}`}
            style={{ left: drag.x, top: drag.y }}
            aria-hidden="true"
          >
            <ScanLine size={17} />
            {spec.rule} · {current} {spec.unit}
            <span>{over ? <Check size={16} /> : <ArrowRight size={16} />}</span>
          </div>
        )}
        <div className="lab-controls">
          <div className="time-control">
            <div className="time-control-heading">
              <label htmlFor="lab-time">
                <span className="time-icon">↔</span> 拖動，改變世界
              </label>
              <span>{["原始狀態", "規則已改變", "規則已恢復"][phase]}</span>
            </div>
            <div className="time-track">
              <input
                id="lab-time"
                type="range"
                min="0"
                max="100"
                value={time}
                disabled={scanning}
                onChange={(e) => {
                  setTime(Number(e.target.value));
                  setResult(null);
                }}
                style={{ "--progress": `${time}%` }}
                aria-valuetext={["原始規則", "規則變更", "恢復原始規則"][phase]}
              />
              <span className="time-boundary first" />
              <span className="time-boundary second" />
            </div>
            <div className="time-labels">
              <span>原始規則</span>
              <span>規則變更</span>
              <span>恢復原狀</span>
            </div>
          </div>
          <div className="lab-guidance">
            <span className="guide-number">02</span>
            <p>
              {stale
                ? "拖曳規則，更新記憶。"
                : "再改變一次世界，看看會發生什麼。"}
              <small>也能點擊規則卡片下方按鈕</small>
            </p>
            <button
              aria-label="查證現行規則並更新記憶"
              className="sync-shortcut"
              disabled={scanning}
              onClick={sync}
            >
              <ScanLine size={17} />
              <span>查證</span>
            </button>
          </div>
        </div>
        <div
          className={`action-experiment ${result ? (result.correct ? "correct" : "incorrect") : ""}`}
        >
          <div className="order-token">
            <Package size={22} />
          </div>
          <div className="action-copy">
            <span>{spec.item}</span>
            <p aria-live="polite">
              {!result
                ? "如果現在依照記憶做決定，會發生什麼？"
                : result.correct
                  ? result.decision
                    ? "判斷正確，世界允許執行。"
                    : "判斷正確，依現行規則拒絕。"
                  : result.decision
                    ? "記憶說可以，世界卻擋下了操作。"
                    : "記憶太保守，拒絕了原本可以處理的訂單。"}
            </p>
          </div>
          <button className="try-action" disabled={scanning} onClick={act}>
            {result ? (
              result.correct ? (
                <Check size={16} />
              ) : (
                <X size={16} />
              )
            ) : (
              <Play size={14} />
            )}{" "}
            依記憶行動
          </button>
          <span className="read-meter">查證 {reads} 次</span>
        </div>
      </section>
      <div className="lab-footnote">
        <span>
          01 改變世界 <ArrowRight size={12} /> 02 更新記憶{" "}
          <ArrowRight size={12} /> 03 驗證行動
        </span>
        <p>上述為確定性教學示意；真模型的成功與失敗，完整保留在實驗紀錄。</p>
      </div>
    </>
  );
}
