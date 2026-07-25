"use client";

import { useEffect, useState } from "react";
import {
  checkFreighterInstalled,
  connectFreighterWallet,
  getConnectedAddress,
  shortenAddress,
} from "@/lib/freighter";
import {
  createPasskeyWallet,
  connectPasskeyWallet,
  isPasskeySupported,
  hasLocalPasskeyWallet,
} from "@/lib/passkey";

export type ConnectedWallet = {
  kind: "freighter" | "passkey";
  address: string;
};

export interface WalletConnectProps {
  onWalletChange: (wallet: ConnectedWallet | null) => void;
}

export function WalletConnect({ onWalletChange }: WalletConnectProps) {
  const [wallet, setWallet] = useState<ConnectedWallet | null>(null);
  const [freighterLoading, setFreighterLoading] = useState(false);
  const [passkeyLoading, setPasskeyLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [passkeySupported, setPasskeySupported] = useState(false);

  useEffect(() => {
    setPasskeySupported(isPasskeySupported());
  }, []);

  useEffect(() => {
    async function hydrateFreighter() {
      const { installed, error: installError } = await checkFreighterInstalled();
      if (!installed) {
        if (installError) setError(installError);
        return;
      }

      const { address, error: addressError } = await getConnectedAddress();
      if (addressError) {
        setError(addressError);
        return;
      }

      if (address) {
        const next: ConnectedWallet = { kind: "freighter", address };
        setWallet(next);
        onWalletChange(next);
      }
    }

    hydrateFreighter();
    // Only ever hydrate once on mount — onWalletChange is a stable
    // callback prop from the parent, not a dependency that should
    // re-trigger this.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleConnectFreighter() {
    setFreighterLoading(true);
    setError(null);

    try {
      const { installed, error: installError } = await checkFreighterInstalled();
      if (!installed) {
        setError(installError ?? "Install Freighter to continue");
        return;
      }

      const { address, error: connectError } = await connectFreighterWallet();
      if (connectError) {
        setError(connectError);
        return;
      }

      if (address) {
        const next: ConnectedWallet = { kind: "freighter", address };
        setWallet(next);
        onWalletChange(next);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Wallet connection failed");
    } finally {
      setFreighterLoading(false);
    }
  }

  async function handleConnectPasskey() {
    setPasskeyLoading(true);
    setError(null);

    try {
      let result;
      if (hasLocalPasskeyWallet()) {
        try {
          result = await connectPasskeyWallet();
        } catch {
          // Stored locally but the live ceremony didn't resolve to a
          // wallet (e.g. cleared credential) — fall back to creating one.
          result = await createPasskeyWallet(`aurum-${Date.now()}`);
        }
      } else {
        // First time on this device — nothing to connect to yet, so skip
        // straight to registration instead of waiting out a ~60s WebAuthn
        // discovery timeout first.
        result = await createPasskeyWallet(`aurum-${Date.now()}`);
      }

      const next: ConnectedWallet = { kind: "passkey", address: result.contractId };
      setWallet(next);
      onWalletChange(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Passkey sign-in failed");
    } finally {
      setPasskeyLoading(false);
    }
  }

  function handleDisconnect() {
    setWallet(null);
    setError(null);
    onWalletChange(null);
  }

  return (
    <div className="flex flex-col items-end gap-3">
      {wallet ? (
        <div className="flex items-center gap-2">
          <span className="rounded-full border border-line bg-surface px-2 py-0.5 font-mono text-[10px] uppercase tracking-wide text-muted">
            {wallet.kind === "passkey" ? "Passkey" : "Freighter"}
          </span>
          <p className="font-mono text-xs text-muted">{shortenAddress(wallet.address)}</p>
          <button
            onClick={handleDisconnect}
            className="rounded-md border border-line bg-surface px-3 py-1.5 font-display text-xs font-medium text-ink transition-colors hover:border-gold/40"
          >
            Disconnect
          </button>
        </div>
      ) : (
        <div className="flex items-center gap-2">
          <button
            onClick={handleConnectFreighter}
            disabled={freighterLoading}
            className="rounded-md bg-gold px-3 py-1.5 font-display text-xs font-semibold text-base transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {freighterLoading ? "Connecting…" : "Connect Freighter"}
          </button>
          {passkeySupported && (
            <button
              onClick={handleConnectPasskey}
              disabled={passkeyLoading}
              className="rounded-md border border-gold/40 px-3 py-1.5 font-display text-xs font-semibold text-gold transition-colors hover:bg-gold/10 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {passkeyLoading ? "Signing in…" : "Sign with passkey"}
            </button>
          )}
        </div>
      )}

      {error && (
        <p className="max-w-xs text-right font-display text-xs text-critical">{error}</p>
      )}
    </div>
  );
}
