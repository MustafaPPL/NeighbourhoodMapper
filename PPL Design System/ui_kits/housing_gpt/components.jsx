/* @jsx React.createElement */
const { useState, useEffect, useRef } = React;

// ============================================================
//  PPL HousingGPT — UI Kit
//  Reusable JSX components that recreate the Supported Housing tool
//  Import colors_and_type.css from the design-system root.
// ============================================================

function Logomark({ product = "Supported Housing", eyebrow = "Knowledge" }) {
  return (
    <div className="pk-logomark">
      <div className="pk-ppl" role="img" aria-label="PPL" />
      <div className="pk-divider" />
      <div className="pk-product">
        <span className="pk-eyebrow">{eyebrow}</span>
        <span className="pk-name">{product}</span>
      </div>
    </div>
  );
}

function SyncCard({ status, files, model, embed }) {
  const [syncing, setSyncing] = useState(false);
  const [text, setText] = useState(status || `Last synced 12 min ago · ${files} files`);
  const trigger = () => {
    setSyncing(true);
    setText("Syncing…");
    setTimeout(() => {
      setSyncing(false);
      setText(`Last synced just now · ${files} files`);
    }, 1400);
  };
  return (
    <div className="pk-sync">
      <div className="pk-sidebar-label">SharePoint sync</div>
      <div className="pk-sync-card">
        <div className="pk-sync-eyebrow">Status</div>
        <div className="pk-sync-status">{text}</div>
        <div className="pk-sync-meta">
          <div><span>Source</span><span>/Supported Housing</span></div>
          <div><span>Model</span><span>{model}</span></div>
          <div><span>Embeddings</span><span>{embed}</span></div>
        </div>
        <button className={`pk-sync-btn ${syncing ? "is-syncing" : ""}`} onClick={trigger}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 12a9 9 0 0 1-9 9"/><path d="M3 12a9 9 0 0 1 9-9"/><path d="M21 3v6h-6"/><path d="M3 21v-6h6"/>
          </svg>
          Sync now
        </button>
      </div>
    </div>
  );
}

function UserChip({ initials, name, role }) {
  return (
    <div className="pk-user-chip">
      <div className="pk-avatar">{initials}</div>
      <div>
        <div className="pk-user-name">{name}</div>
        <div className="pk-user-role">{role}</div>
      </div>
    </div>
  );
}

function Sidebar({ children }) { return <aside className="pk-sidebar">{children}</aside>; }

function PromptChips({ prompts, onPick }) {
  return (
    <div className="pk-chips">
      {prompts.map((p, i) => (
        <button key={i} className="pk-chip" onClick={() => onPick(p.q)}>
          {p.label}
        </button>
      ))}
    </div>
  );
}

function Composer({ value, onChange, onSubmit, disabled }) {
  const ref = useRef(null);
  useEffect(() => {
    const el = ref.current; if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 180) + "px";
  }, [value]);
  return (
    <form className="pk-composer" onSubmit={(e)=>{e.preventDefault(); if(!disabled) onSubmit();}}>
      <textarea
        ref={ref}
        rows={1}
        value={value}
        onChange={(e)=>onChange(e.target.value)}
        onKeyDown={(e)=>{ if(e.key==="Enter" && !e.shiftKey){ e.preventDefault(); if(!disabled) onSubmit(); } }}
        placeholder="Ask about policy, procedure, competitor insight or operational guidance…"
      />
      <div className="pk-composer-row">
        <div className="pk-composer-left">
          <button type="button" className="pk-mini">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>
            Attach
          </button>
          <button type="button" className="pk-mini pk-active">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="9"/><path d="M3.6 9h16.8M3.6 15h16.8M12 3a15 15 0 0 1 0 18M12 3a15 15 0 0 0 0 18"/></svg>
            Supported Housing
          </button>
        </div>
        <div className="pk-composer-right">
          <span className="pk-hint">Enter to send</span>
          <button type="submit" className="pk-send" disabled={disabled}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="19" x2="12" y2="5"/><polyline points="5 12 12 5 19 12"/></svg>
          </button>
        </div>
      </div>
    </form>
  );
}

function Message({ role, content, citations }) {
  return (
    <div className={`pk-msg pk-msg-${role}`}>
      <div className="pk-msg-body">{content}</div>
      {citations && (
        <div className="pk-cites">
          {citations.map((c, i) => (
            <span key={i} className="pk-cite">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/></svg>
              {c.title}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function Hero({ onPick }) {
  const prompts = [
    { label: "Voids recovery — relet targets", q: "What does the voids recovery policy say about target relet times for supported housing schemes?" },
    { label: "Duty to refer under HRA", q: "Summarise the duty to refer obligations under the Homelessness Reduction Act for commissioned supported housing." },
    { label: "Eligible service charges", q: "Which service charges are eligible for Housing Benefit in exempt accommodation, and what risks are flagged in our internal notes?" },
    { label: "Move-on pathway patterns", q: "What patterns have we seen in the Salford, Islington and Bury move-on pathway evaluations?" }
  ];
  return (
    <div className="pk-hero">
      <div className="pk-hero-mark" aria-hidden="true" />
      <PromptChips prompts={prompts} onPick={onPick} />
    </div>
  );
}

Object.assign(window, { Logomark, SyncCard, UserChip, Sidebar, Composer, Message, Hero, PromptChips });
