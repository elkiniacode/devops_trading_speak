import { useId, useState } from "react";

import type { PhoneBody } from "@/lib/charla/types";
import { phoneError } from "@/lib/charla/validate";

import s from "../Sala.module.css";
import { ClockIcon } from "./parts";

const CONSENT_ERROR = "Necesitamos tu autorización para escribirte por WhatsApp.";

/**
 * Near the end of the talk: an optional WhatsApp number for the result and the slides.
 * `onSubmit` resolves to a Spanish error message, or null once the server accepted it.
 */
export function PhoneView({ onSubmit }: { onSubmit: (body: PhoneBody) => Promise<string | null> }) {
  const id = useId();
  const [phone, setPhone] = useState("");
  const [consent, setConsent] = useState(false);
  const [tried, setTried] = useState(false);
  const [busy, setBusy] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);

  const phoneMsg = tried ? phoneError(phone) : null;
  const consentMsg = tried && !consent ? CONSENT_ERROR : null;

  async function send(body: PhoneBody) {
    setBusy(true);
    setServerError(null);
    const error = await onSubmit(body);
    setBusy(false);
    setServerError(error);
  }

  return (
    <form
      className={`${s.view} ${s.rise}`}
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        setTried(true);
        if (busy || phoneError(phone) || !consent) return;
        void send({ phone: phone.trim(), consent: true });
      }}
    >
      <div className={s.amber}>
        <ClockIcon size={14} />
        <span>La charla está por terminar</span>
      </div>
      <span className={s.kicker}>ÚLTIMO PASO · OPCIONAL</span>
      <h2 className={`holo ${s.titleSm}`}>Recibe tu resultado y las diapositivas</h2>
      <p className={s.lead}>Te enviamos por WhatsApp tu puesto final y las diapositivas de la charla.</p>

      <div className={s.field}>
        <label htmlFor={id} className={s.fieldLabel}>
          CELULAR
        </label>
        <div className={s.phoneRow}>
          <span className={s.prefix}>+57</span>
          <input
            id={id}
            className={phoneMsg ? `${s.fld} ${s.fldErr}` : s.fld}
            type="tel"
            inputMode="numeric"
            autoComplete="tel-national"
            placeholder="300 123 4567"
            maxLength={16}
            value={phone}
            aria-invalid={phoneMsg ? true : undefined}
            onChange={(e) => setPhone(e.target.value.replace(/[^\d ]/g, ""))}
            data-testid="sala-phone-input"
          />
        </div>
        {phoneMsg && <span className={s.err}>{phoneMsg}</span>}
      </div>

      <label className={s.check}>
        <input
          type="checkbox"
          className={s.checkInput}
          checked={consent}
          onChange={(e) => setConsent(e.target.checked)}
          data-testid="sala-phone-consent"
        />
        <span className={s.checkBox} aria-hidden="true">
          {consent && (
            <svg width="12" height="12" viewBox="0 0 12 12">
              <path d="M2 6.4 L4.8 9.2 L10.2 2.8" fill="none" stroke="currentColor" strokeWidth="2" />
            </svg>
          )}
        </span>
        <span className={s.checkText}>
          Autorizo contactarme por WhatsApp para enviarme el resultado, las diapositivas y novedades de IA Revolutions.
        </span>
      </label>
      {consentMsg && <span className={s.err}>{consentMsg}</span>}
      {serverError && (
        <span className={s.err} role="alert">
          {serverError}
        </span>
      )}

      <div className={s.actions}>
        <button type="submit" className={s.btn} disabled={busy} data-testid="sala-phone-send">
          ENVIARME TODO
        </button>
        <button
          type="button"
          className={s.linkBtn}
          disabled={busy}
          onClick={() => void send({ skip: true })}
          data-testid="sala-phone-skip"
        >
          Ahora no
        </button>
      </div>
    </form>
  );
}
