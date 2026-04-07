$src = "d:\superbrain\backend"
$dest = "d:\superbrain\superbrain-cli\payload"

if (Test-Path $dest) { Remove-Item $dest\* -Recurse -Force }
New-Item -ItemType Directory -Force -Path $dest | Out-Null
Copy-Item $src\* $dest -Recurse -Force -Exclude '.venv', '__pycache__', 'config', 'superbrain.db', '*.sqlite', '*.log', 'token.txt', 'err.json', 'failures.txt', 'final_test.txt', 'yt_error.txt'

$destConfig = "$dest\config"
New-Item -ItemType Directory -Force -Path $destConfig | Out-Null
Copy-Item $src\config\* $destConfig -Recurse -Force -Exclude '.api_keys', 'ngrok_token.txt', 'ngrok_enabled.txt', 'localtunnel.log'
