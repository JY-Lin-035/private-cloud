// Generates a build id shared by: vite define(__BUILD_TS__) and public/version.json
import { writeFileSync, existsSync, readFileSync, mkdirSync } from 'node:fs'
const id = process.env.BUILD_ID || String(Date.now())
writeFileSync('.buildid', id)
if (!existsSync('public')) mkdirSync('public')
writeFileSync('public/version.json', JSON.stringify({ v: id }))
console.log('build id:', id)
