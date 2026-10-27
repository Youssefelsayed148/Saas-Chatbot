/**
 * The widget's stylesheet, shared by the sandboxed frame and the settings
 * preview so both render the same CSS. Moved out of the frame page unchanged
 * apart from the theme variables (#14): every `--w-*` lookup falls back to the
 * previous value, so an unthemed widget looks exactly as before.
 */
export const widgetStyles = `
html,body{height:100%}
.widget-frame{position:absolute;inset:0;display:flex;flex-direction:column;height:100%;background:var(--surface);color:var(--w-text,var(--text));font-family:var(--font);font-size:14px;overflow:hidden}
.widget-header{display:grid;grid-template-columns:32px 1fr 44px;column-gap:.6rem;align-items:center;padding:1rem 1.1rem;background:var(--w-header,var(--widget-brand));color:var(--w-header-ink,var(--widget-ink,var(--ink-light)));flex-shrink:0}
.widget-header-caption{grid-column:2;grid-row:2}.widget-close{grid-column:3;grid-row:1/3;background:transparent;color:inherit;border:1px solid currentColor;min-inline-size:44px;min-block-size:44px;padding:0;font-size:1.3rem}.widget-close:focus-visible{outline-color:currentColor}
.widget-brand-mark{grid-row:1/3;font-size:1.8rem;line-height:1}.widget-title{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-weight:650;font-size:.95rem}.widget-header-caption{font-size:.7rem;opacity:.9}
.widget-frame .widget-thread{flex:1 1 0;overflow-y:auto;overscroll-behavior:contain;padding:1.1rem;display:flex;flex-direction:column;gap:.8rem;min-height:0;inline-size:100%;max-inline-size:none;margin:0;scrollbar-width:thin;scrollbar-color:var(--border) transparent}
.widget-turns{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:.85rem}
.widget-bubble{background:var(--w-bot-bubble,var(--surface-raised));color:var(--w-text,var(--text));border:1px solid var(--border);border-radius:var(--radius) var(--radius) var(--radius) 4px;padding:.85rem 1rem;max-inline-size:92%;align-self:flex-start;overflow-wrap:anywhere;line-height:1.65}
.widget-bubble:not(.visitor){overflow-wrap:anywhere}
.widget-bubble.visitor{background:var(--w-user-bubble,var(--widget-brand));color:var(--w-user-bubble-ink,var(--widget-ink,var(--ink-light)));align-self:flex-end;border-color:transparent;border-radius:var(--radius) var(--radius) 4px var(--radius)}
[dir=rtl] .widget-bubble{border-radius:var(--radius) var(--radius) 4px var(--radius)}[dir=rtl] .widget-bubble.visitor{border-radius:var(--radius) var(--radius) var(--radius) 4px}
.widget-citations{list-style:none;margin:.6rem 0 0;padding:0;display:flex;flex-wrap:wrap;gap:.3rem}.widget-source-chip{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-sm);padding:.2rem .5rem;font-size:.7rem}.widget-source-chip a{color:var(--accent);text-decoration:none}
.widget-feedback{display:flex;gap:.4rem;margin-block-start:.5rem}.widget-feedback button{background:transparent;color:var(--text);border:1px solid var(--border);border-radius:var(--radius-sm);cursor:pointer;font-size:.85rem;padding:.25rem .45rem;min-block-size:32px}.widget-feedback-done{display:block;font-size:.7rem;margin-block-start:.4rem}.widget-handoff{font-size:.75rem;color:var(--warning);border-block-start:1px solid var(--border);padding-block-start:.4rem;margin-block:.5rem 0}
.widget-note{flex-shrink:0;padding:.5rem .2rem;color:var(--muted);font-size:.85rem;margin:0}.widget-note.error{color:var(--danger);background:var(--danger-soft);border:1px solid var(--border);border-radius:var(--radius-sm);padding:.7rem}.widget-note.error button{display:block;margin-block-start:.5rem;font-size:.75rem}
.widget-chips{display:flex;flex-wrap:wrap;gap:.5rem;margin-block-start:.5rem}.widget-chip{background:var(--surface);color:var(--accent);border:1px solid var(--border);border-radius:999px;padding:.5rem .8rem;font-size:.8rem;cursor:pointer;min-block-size:40px}
.widget-frame .widget-composer{display:flex;flex-direction:row;gap:.5rem;padding:.85rem 1rem;border-block-start:1px solid var(--border);background:var(--surface);margin:0;max-inline-size:none;flex-shrink:0;inline-size:100%}
.widget-composer-label{position:absolute;inline-size:1px;block-size:1px;overflow:hidden;clip-path:inset(50%)}.widget-composer input{flex:1;border:1px solid var(--border);border-radius:var(--radius-sm);padding:.65rem .8rem;font:inherit;min-inline-size:0;background:var(--bg);color:var(--text)}.widget-composer button{background:var(--w-send,var(--widget-brand));color:var(--w-send-ink,var(--widget-ink,var(--ink-light)));border:0;border-radius:var(--radius-sm);padding:.65rem .9rem;cursor:pointer;align-self:stretch}.widget-composer button:disabled{opacity:.6;cursor:progress}
.widget-contact-bar{display:flex;justify-content:flex-end;padding:.4rem 1rem 0;background:var(--surface);flex-shrink:0}
.widget-contact-btn{display:inline-flex;align-items:center;gap:.45rem;background:var(--w-send,var(--widget-brand));color:var(--w-send-ink,var(--widget-ink,var(--ink-light)));border:0;border-radius:999px;padding:.45rem .95rem;min-block-size:36px;font-size:.8rem;font-weight:650;cursor:pointer;box-shadow:0 2px 8px rgba(0,0,0,.22);transition:transform .15s ease,box-shadow .15s ease}
.widget-contact-btn:hover{transform:translateY(-1px);box-shadow:0 4px 12px rgba(0,0,0,.3)}.widget-contact-btn:active{transform:none}
.widget-sheet-layer{position:absolute;inset:0;z-index:5;display:flex;flex-direction:column;justify-content:flex-end}
.widget-sheet-backdrop{position:absolute;inset:0;border:0;padding:0;min-block-size:0;background:rgba(2,6,23,.55);cursor:default;animation:widget-fade .2s ease-out}
.widget-sheet{position:relative;max-block-size:94%;overflow-y:auto;background:var(--surface);color:var(--w-text,var(--text));border-radius:20px 20px 0 0;padding:1rem 1.1rem 1.2rem;box-shadow:0 -12px 32px rgba(0,0,0,.35);animation:widget-sheet-in .26s cubic-bezier(.2,.8,.2,1);scrollbar-width:thin}
.widget-sheet-head{display:flex;justify-content:space-between;align-items:flex-start;gap:.75rem;margin-block-end:.85rem}
.widget-sheet-head h2{font-size:1.05rem;margin:0 0 .2rem}.widget-sheet-head p{margin:0;color:var(--muted);font-size:.8rem;line-height:1.45}
.widget-sheet-close{background:transparent;color:var(--muted);border:1px solid var(--border);border-radius:999px;min-inline-size:32px;min-block-size:32px;padding:0;cursor:pointer;flex-shrink:0}
.widget-lead-form{display:flex;flex-direction:column;gap:.7rem;inline-size:100%;max-inline-size:none}
.widget-field{position:relative;display:block}
.widget-field input{inline-size:100%;box-sizing:border-box;padding:1.35rem .85rem .45rem;border:1px solid var(--border);border-radius:12px;background:var(--bg);color:var(--text);font:inherit;min-block-size:48px;transition:border-color .15s,box-shadow .15s}
.widget-field span{position:absolute;inset-inline-start:.85rem;top:50%;transform:translateY(-50%);color:var(--muted);font-size:.85rem;pointer-events:none;transition:all .15s ease}
.widget-field input:focus+span,.widget-field input:not(:placeholder-shown)+span{top:.55rem;transform:none;font-size:.68rem;color:var(--accent)}
.widget-field input:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px color-mix(in srgb,var(--accent) 25%,transparent)}
.widget-field input[aria-invalid=true]{border-color:var(--danger)}
.widget-lead-consent{display:flex;flex-direction:row;align-items:flex-start;gap:.6rem;font-size:.75rem;line-height:1.45;color:var(--muted)}
.widget-lead-consent input{inline-size:18px;block-size:18px;margin:.1rem 0 0;flex-shrink:0;accent-color:var(--accent)}
.widget-lead-submit{display:inline-flex;align-items:center;justify-content:center;gap:.5rem;background:var(--w-send,var(--widget-brand));color:var(--w-send-ink,var(--widget-ink,var(--ink-light)));border:0;border-radius:12px;min-block-size:48px;font-weight:650;font-size:.9rem;cursor:pointer;transition:transform .15s,opacity .15s}
.widget-lead-submit:hover:not(:disabled){transform:translateY(-1px)}.widget-lead-submit:disabled{opacity:.7;cursor:progress}
.widget-spinner{inline-size:16px;block-size:16px;border:2px solid currentColor;border-right-color:transparent;border-radius:50%;animation:widget-spin .7s linear infinite}
.widget-note[data-testid=widget-lead-done]{display:flex;align-items:center;padding:.5rem 1rem}
.widget-done-mark{display:inline-grid;place-items:center;inline-size:20px;block-size:20px;margin-inline-end:.5rem;border-radius:50%;background:var(--success,#16a34a);color:#fff;font-size:.75rem;flex-shrink:0;animation:widget-pop .3s ease-out}
@keyframes widget-sheet-in{from{transform:translateY(100%)}to{transform:none}}@keyframes widget-fade{from{opacity:0}to{opacity:1}}@keyframes widget-spin{to{transform:rotate(360deg)}}@keyframes widget-pop{from{transform:scale(.3);opacity:0}to{transform:none;opacity:1}}
@media(prefers-reduced-motion:reduce){.widget-sheet,.widget-sheet-backdrop,.widget-spinner,.widget-done-mark,.widget-contact-btn{animation:none;transition:none}}
.typing-dots{display:inline-flex;gap:4px;padding:.65rem .8rem;border:1px solid var(--border);border-radius:999px;background:var(--surface-raised)}.typing-dots i{inline-size:5px;block-size:5px;background:var(--muted);border-radius:50%;animation:widget-pulse .8s ease-in-out infinite alternate}.typing-dots i:nth-child(2){animation-delay:.15s}.typing-dots i:nth-child(3){animation-delay:.3s}@keyframes widget-pulse{to{opacity:.3;transform:translateY(-3px)}}
@media(prefers-reduced-motion:reduce){.typing-dots i{animation:none}}
.widget-frame[data-widget-variant=glass]{background:linear-gradient(160deg,#0f172a 0%,#1e1b4b 55%,#312e81 100%)}
.widget-frame[data-widget-variant=glass] .widget-bubble:not(.visitor){background:color-mix(in srgb,var(--w-bot-bubble,#1e293b) 62%,transparent);border-color:rgba(255,255,255,.2);backdrop-filter:blur(10px)}
.widget-frame[data-widget-variant=glass] .widget-composer{background:rgba(15,23,42,.55);border-block-start-color:rgba(255,255,255,.14)}
.widget-frame[data-widget-variant=glass] .widget-composer input{background:rgba(255,255,255,.08);color:var(--w-text,#f1f5f9);border-color:rgba(255,255,255,.2)}
.widget-frame[data-widget-variant=glass] .widget-note{color:#cbd5e1}
.widget-frame[data-widget-variant=glass] .widget-contact-bar{background:rgba(15,23,42,.55)}
.widget-frame[data-widget-variant=glass] .widget-sheet{background:#1e1b4b;color:#f1f5f9}
`;
