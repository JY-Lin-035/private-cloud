# private-cloud
簡述等待設計中...
## 環境建置
在開始前請先安裝以下工具:

0. Scoop
    - (若要指定位置) $env:SCOOP='D:\your-path'; [Environment]::SetEnvironmentVariable('SCOOP', $env:SCOOP, 'User')
    - Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
    - irm get.scoop.sh | iex
1. nvm
    - scoop install nvm
2. Node.js
    - nvm install lts
    - nvm use lts
3. pnpm
    - npm install -g pnpm
4. uv
    - scoop install uv
