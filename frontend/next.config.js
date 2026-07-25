/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // sac-sdk (a passkey-kit dependency) ships raw TypeScript as its main
  // entry instead of compiled JS; Next's webpack skips transpiling
  // node_modules by default, so this package needs to opt in explicitly.
  transpilePackages: ["sac-sdk"],
};

module.exports = nextConfig;
