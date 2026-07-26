"use client";

import { PasskeyKit } from "passkey-kit";
import type { AssembledTransaction } from "@stellar/stellar-sdk/contract";

const TESTNET_RPC_URL = "https://soroban-testnet.stellar.org";
const TESTNET_NETWORK_PASSPHRASE = "Test SDF Network ; September 2015";

// Canonical passkey-kit v1 smart-wallet WASM hash on testnet — see
// https://github.com/kalepail/passkey-kit/blob/main/docs/deployments-testnet-2026-07-11.md
const TESTNET_WALLET_WASM_HASH =
  "fdefad64b96837147e1c333e51f537b696eab925e9f147e63d597c04e3c903f0";

const APP_NAME = "Aurum";
const RELAYER_SUBMIT_PATH = "/relayer/submit";
const HAS_WALLET_STORAGE_KEY = "aurum:hasPasskeyWallet";

let kitInstance: PasskeyKit | null = null;

function getKit(): PasskeyKit {
  if (!kitInstance) {
    kitInstance = new PasskeyKit({
      rpcUrl: TESTNET_RPC_URL,
      networkPassphrase: TESTNET_NETWORK_PASSPHRASE,
      walletWasmHash: TESTNET_WALLET_WASM_HASH,
    });
  }
  return kitInstance;
}

/**
 * Feature-detects WebAuthn support so callers can fall back to Freighter
 * gracefully instead of showing a passkey option that will fail. Testnet
 * platform authenticator availability (Face ID / Touch ID / hardware keys)
 * isn't checked here — only that the browser API exists — since that check
 * is itself async and best done lazily, not on every render.
 */
export function isPasskeySupported(): boolean {
  if (typeof window === "undefined") return false;
  return typeof window.PublicKeyCredential !== "undefined";
}

/**
 * Whether a passkey wallet has previously been created on this device.
 * `connectWallet()`'s discovery ceremony runs a live WebAuthn `get()` call
 * that only resolves once its ~60s timeout expires if no matching
 * credential exists — worth avoiding for a first-time user, who has
 * nothing to connect to yet and should go straight to `createWallet()`.
 */
export function hasLocalPasskeyWallet(): boolean {
  if (typeof window === "undefined") return false;
  return window.localStorage.getItem(HAS_WALLET_STORAGE_KEY) === "true";
}

function markLocalPasskeyWalletCreated(): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(HAS_WALLET_STORAGE_KEY, "true");
}

export interface PasskeyWallet {
  contractId: string;
  keyId: string;
}

async function submitViaRelayer(signedXdr: string): Promise<{ hash: string }> {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  const res = await fetch(`${apiUrl}${RELAYER_SUBMIT_PATH}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ xdr: signedXdr }),
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Relayer submission failed (${res.status}): ${body}`);
  }

  const result = await res.json();
  if (!result.success) {
    throw new Error(result.error ?? "Relayer submission failed");
  }
  return { hash: result.hash };
}

/**
 * Runs the WebAuthn registration ceremony, deploys a new smart-wallet
 * contract initialized with that passkey as its only signer, and submits
 * the deploy transaction through our own backend relayer (not passkey-kit's
 * built-in OpenZeppelin-relayer path — see the design doc).
 */
export async function createPasskeyWallet(
  userLabel: string,
): Promise<PasskeyWallet> {
  const kit = getKit();
  const { contractId, keyIdBase64, signedTx } = await kit.createWallet(
    APP_NAME,
    userLabel,
  );
  await submitViaRelayer(signedTx);
  markLocalPasskeyWalletCreated();
  return { contractId, keyId: keyIdBase64 };
}

/**
 * Reconnects a previously created passkey wallet. Throws if the passkey
 * ceremony fails or doesn't resolve to a live signer on any wallet.
 */
export async function connectPasskeyWallet(): Promise<PasskeyWallet> {
  const kit = getKit();
  const { contractId, keyIdBase64 } = await kit.connectWallet();
  return { contractId, keyId: keyIdBase64 };
}

/**
 * Signs every wallet auth entry of an assembled Soroban transaction with
 * the connected passkey, then submits it through the backend relayer.
 */
export async function signAndSubmitWithPasskey(
  txn: AssembledTransaction<unknown>,
): Promise<{ hash: string }> {
  const kit = getKit();
  const signed = await kit.sign(txn);
  return submitViaRelayer(signed.toXDR());
}
