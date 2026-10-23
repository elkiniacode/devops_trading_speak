"use client";

import { useEffect, useState } from "react";

import styles from "./presenter.module.css";

/** Big QR (Elkin's /charla/qr.png) plus the join URL. Without the image, just the URL. */
export function QrOverlay({ onClose }: { onClose: () => void }) {
  const [hasImage, setHasImage] = useState(true);
  const [url, setUrl] = useState("/charla/");
  useEffect(() => setUrl(`${window.location.origin}/charla/`), []);
  return (
    <div className={styles.overlay} role="dialog" aria-label="Código QR de la charla" data-testid="pres-qr" onClick={onClose}>
      <div className={styles.qrCard}>
        <span className="c-kicker">ESCANEA Y ENTRA</span>
        {hasImage ? (
          <img
            src="/charla/qr.png"
            alt="Código QR para entrar a la charla"
            className={styles.qrImage}
            onError={() => setHasImage(false)}
            data-testid="pres-qr-image"
          />
        ) : null}
        <span className={styles.qrUrl} data-testid="pres-qr-url">
          {url}
        </span>
      </div>
    </div>
  );
}
