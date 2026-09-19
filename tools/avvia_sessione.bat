<# : parte batch - rilancia questo stesso file in PowerShell, che per lui e' tutto commento fino a #>
@echo off
set "BP_DIR=%~dp0"
powershell -NoProfile -Command "iex (Get-Content -LiteralPath '%~f0' -Raw)"
exit /b
#>
# Chiede durata, potenziamenti e mura, poi avvia BasePilot. Va nella stessa cartella di BasePilot.exe.
Add-Type -AssemblyName System.Windows.Forms
[Windows.Forms.Application]::EnableVisualStyles()

$exe = Join-Path $env:BP_DIR 'BasePilot.exe'
if (-not (Test-Path $exe)) { [void][Windows.Forms.MessageBox]::Show("Non trovo $exe", 'BasePilot'); exit }

$form = New-Object Windows.Forms.Form -Property @{ Text = 'BasePilot'; FormBorderStyle = 'FixedDialog'; StartPosition = 'CenterScreen'; MaximizeBox = $false; MinimizeBox = $false; AutoSize = $true; AutoSizeMode = 'GrowAndShrink'; TopMost = $true }
$grid = New-Object Windows.Forms.TableLayoutPanel -Property @{ ColumnCount = 2; AutoSize = $true; Padding = 10 }
$minutes = New-Object Windows.Forms.NumericUpDown -Property @{ Minimum = 1; Maximum = 999; Value = 60 }
$mode = New-Object Windows.Forms.ComboBox -Property @{ DropDownStyle = 'DropDownList'; Width = 240 }
[void]$mode.Items.AddRange(@('maxer - tutto tranne il Municipio', 'rusher - anche il Municipio', 'dry - scrive nel log, non spende', 'off - solo farm'))
$mode.SelectedIndex = 0
$walls = New-Object Windows.Forms.CheckBox -Property @{ Text = 'Compra mura'; Checked = $true; AutoSize = $true }
$start = New-Object Windows.Forms.Button -Property @{ Text = 'Avvia'; DialogResult = 'OK' }
$form.AcceptButton = $start

$grid.Controls.Add((New-Object Windows.Forms.Label -Property @{ Text = 'Durata (minuti)'; AutoSize = $true; Anchor = 'Left' }), 0, 0)
$grid.Controls.Add($minutes, 1, 0)
$grid.Controls.Add((New-Object Windows.Forms.Label -Property @{ Text = 'Potenziamenti'; AutoSize = $true; Anchor = 'Left' }), 0, 1)
$grid.Controls.Add($mode, 1, 1)
$grid.Controls.Add($walls, 1, 2)
$grid.Controls.Add($start, 1, 3)
$form.Controls.Add($grid)

if ($form.ShowDialog() -ne 'OK') { exit }

$argv = @('--autostart', '--minutes', "$([int]$minutes.Value)", '--upgrades', $mode.Text.Split(' ')[0])
if ($walls.Checked) { $argv += '--walls' }

# Finita la sessione la finestra resta aperta, e due copie cliccherebbero sullo stesso gioco.
Get-Process BasePilot -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Process $exe -ArgumentList $argv
