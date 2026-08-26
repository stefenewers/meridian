/** @type {import('next').NextConfig} */
const path = require('path')

const nextConfig = {
  reactStrictMode: true,
  // The shared types package is source-only, so it has to be compiled with the app.
  transpilePackages: ['@meridian/shared'],
  outputFileTracingRoot: path.join(__dirname, '../../'),
}

module.exports = nextConfig
