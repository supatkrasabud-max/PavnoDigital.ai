# PAVNO mascots v2 - soft "bold and easy / cozy kawaii" style.
# Builds 24 colour SVGs into dist/assets/mascots and matching colouring-page
# line art into design/mascots-lineart.  Run:  powershell -File scripts/build-mascots.ps1
# Style rules: thick warm outline, big low-set sparkly eyes, mochi-shaped head,
# tilted head + waving arm so nothing looks stiff, soft pastel fills.
[Threading.Thread]::CurrentThread.CurrentCulture = [Globalization.CultureInfo]::InvariantCulture
$root = Split-Path $PSScriptRoot -Parent
$outColor = Join-Path $root 'dist\assets\mascots'
$outLine  = Join-Path $root 'design\mascots-lineart'
New-Item -ItemType Directory -Force $outColor, $outLine | Out-Null

$O = '#4a3340'   # outline
$K = '#3a2a33'   # eyes / dark features
$PINK = '#ff8fa8'

function Rnd($n) { [math]::Round([double]$n, 1) }
function St($w = 7) { "stroke='$O' stroke-width='$w' stroke-linejoin='round' stroke-linecap='round'" }
function Mirror($s) { "<g transform='translate(400 0) scale(-1 1)'>$s</g>" }
function Both($s) { $s + (Mirror $s) }
function Tilt($s, $a = -5) { "<g transform='rotate($a 200 200)'>$s</g>" }
function Eye($x, $y, $rx = 13, $ry = 16) {
  "<ellipse data-k='1' cx='$x' cy='$y' rx='$rx' ry='$ry' fill='$K'/>" +
  "<circle data-k='1' cx='$(Rnd ($x - $rx * .3))' cy='$(Rnd ($y - $ry * .36))' r='$(Rnd ($rx * .42))' fill='#fff'/>" +
  "<circle data-k='1' cx='$(Rnd ($x + $rx * .36))' cy='$(Rnd ($y + $ry * .42))' r='$(Rnd ($rx * .2))' fill='#fff'/>"
}
function Blush($cx, $y, $dx, $rx = 17, $ry = 10) {
  "<ellipse data-c='1' cx='$($cx - $dx)' cy='$y' rx='$rx' ry='$ry' fill='$PINK' opacity='.55'/>" +
  "<ellipse data-c='1' cx='$($cx + $dx)' cy='$y' rx='$rx' ry='$ry' fill='$PINK' opacity='.55'/>"
}
function Mouth($cx, $y, $kind = 'smile') {
  switch ($kind) {
    'smile' { "<path d='M$($cx - 11) $y Q$cx $($y + 13) $($cx + 11) $y' fill='none' $(St 5)/>" }
    'w'     { "<path d='M$($cx - 15) $y Q$($cx - 7.5) $($y + 11) $cx $y Q$($cx + 7.5) $($y + 11) $($cx + 15) $y' fill='none' $(St 5)/>" }
    'open'  { "<path d='M$($cx - 13) $y Q$cx $($y + 26) $($cx + 13) $y Z' fill='#f0637d' $(St 5)/>" }
    'none'  { '' }
  }
}
function Face($cx = 200, $cy = 198, $dx = 46, $mouth = 'smile', $my = 22, $rx = 13, $ry = 16) {
  (Eye ($cx - $dx) $cy $rx $ry) + (Eye ($cx + $dx) $cy $rx $ry) + (Blush $cx ($cy + 26) ($dx + 30)) + (Mouth $cx ($cy + $my) $mouth)
}
function Shine($x = 148, $y = 122) { "<ellipse data-c='1' cx='$x' cy='$y' rx='26' ry='11' fill='#fff' opacity='.45' transform='rotate(-28 $x $y)'/>" }
function Head($c) { "<path d='M200 84 C268 84 310 128 308 190 C306 248 262 282 200 282 C138 282 94 248 92 190 C90 128 132 84 200 84Z' fill='$c' $(St)/>" }
function Heart($x, $y, $s = 1, $c = '#ff8fa8') { "<path transform='translate($x $y) scale($s)' d='M0 16 C-22 0 -16 -20 0 -10 C16 -20 22 0 0 16Z' fill='$c' $(St 4)/>" }
function Star($x, $y, $s = 1, $c = '#ffe07a') { "<path transform='translate($x $y) scale($s)' d='M0 -20 L6 -6 L21 -5 L9 5 L13 20 L0 11 L-13 20 L-9 5 L-21 -5 L-6 -6 Z' fill='$c' $(St 4)/>" }
function Tube($d, $c, $w = 17) { "<path d='$d' fill='none' stroke='$O' stroke-width='$($w + 13)' stroke-linecap='round' stroke-linejoin='round'/><path d='$d' fill='none' stroke='$c' stroke-width='$w' stroke-linecap='round' stroke-linejoin='round'/>" }
function Body($c, $belly, $feet = '', $wave = $true) {
  if (-not $feet) { $feet = $c }
  $armL = "<ellipse cx='140' cy='322' rx='17' ry='30' fill='$c' $(St) transform='rotate(24 140 322)'/>"
  if ($wave) { $armR = "<ellipse cx='272' cy='292' rx='17' ry='31' fill='$c' $(St) transform='rotate(40 272 292)'/>" }
  else { $armR = "<ellipse cx='260' cy='322' rx='17' ry='30' fill='$c' $(St) transform='rotate(-24 260 322)'/>" }
  $armL + $armR +
  "<path d='M200 258 C246 258 266 300 262 338 C259 368 236 382 200 382 C164 382 141 368 138 338 C134 300 154 258 200 258Z' fill='$c' $(St)/>" +
  "<ellipse data-c='1' cx='200' cy='334' rx='36' ry='34' fill='$belly'/>" +
  "<ellipse cx='168' cy='378' rx='25' ry='13' fill='$feet' $(St)/><ellipse cx='232' cy='378' rx='25' ry='13' fill='$feet' $(St)/>"
}
$Ground = "<ellipse data-c='1' cx='200' cy='391' rx='96' ry='7' fill='$O' opacity='.1'/>"

$M = [ordered]@{}

# ---------- template animals ----------
$c = '#e2b48a'; $l = '#f8e3c8'
$M.bear = $Ground + (Body $c $l) + (Heart 200 336 1.1) + (Tilt (
  (Both "<circle cx='122' cy='108' r='33' fill='$c' $(St)/><circle data-c='1' cx='122' cy='108' r='16' fill='$l'/>") + (Head $c) + (Shine) +
  "<ellipse cx='200' cy='228' rx='38' ry='27' fill='$l' $(St 5)/><ellipse data-k='1' cx='200' cy='214' rx='12' ry='8' fill='$K'/>" +
  (Eye 152 196) + (Eye 248 196) + (Blush 200 222 80) + (Mouth 200 226)))

$c = '#ffffff'; $l = '#ffe3ea'
$M.bunny = $Ground + "<circle cx='262' cy='352' r='20' fill='$c' $(St)/>" + (Body $c $l) + (Tilt (
  "<ellipse cx='158' cy='76' rx='25' ry='60' fill='$c' $(St) transform='rotate(-8 158 76)'/><ellipse data-c='1' cx='158' cy='82' rx='11' ry='40' fill='#ffc2d4' transform='rotate(-8 158 82)'/>" +
  "<path d='M226 106 C222 52 248 16 276 22 C304 30 300 64 262 112 Z' fill='$c' $(St)/><path data-c='1' d='M240 94 C240 60 256 40 272 40 C284 46 276 66 256 98Z' fill='#ffc2d4'/>" +
  (Head $c) + (Eye 156 200) + (Eye 244 200) + (Blush 200 226 76) +
  "<ellipse cx='200' cy='215' rx='7' ry='5' fill='#f0637d' $(St 4)/>" + (Mouth 200 224 'w')))

$c = '#ffb877'; $l = '#fff0dc'
$M.cat = $Ground + (Tube 'M254 356 C312 356 320 310 300 286' $c) + (Body $c $l) + (Tilt (
  (Both "<path d='M104 150 L110 64 Q150 74 178 104 Z' fill='$c' $(St)/><path data-c='1' d='M119 124 L122 88 Q140 94 154 108 Z' fill='#ffc2d4'/>") + (Head $c) + (Shine) +
  "<path data-c='1' d='M184 92 L188 112 M200 88 L200 112 M216 92 L212 112' fill='none' stroke='#ec9550' stroke-width='7' stroke-linecap='round'/>" +
  (Eye 154 198) + (Eye 246 198) + (Blush 200 224 76) +
  "<path d='M193 212 L207 212 L200 220 Z' fill='#f0637d' $(St 4)/>" + (Mouth 200 224 'w') +
  (Both "<path d='M126 212 L86 204 M126 224 L88 230' fill='none' $(St 4)/>")))

$c = '#f6e0c2'; $d = '#b9855a'
$M.puppy = $Ground + (Tube 'M256 352 C290 346 300 318 292 300' $c 14) + (Body $c '#fff7ea') + (Tilt (
  (Head $c) + (Shine 160 116) + "<ellipse data-c='1' cx='246' cy='196' rx='31' ry='33' fill='#e7b98a'/>" +
  (Both "<path d='M118 106 C78 102 62 160 72 208 C78 234 108 234 114 204 C118 172 124 140 144 114 Z' fill='$d' $(St)/>") +
  "<ellipse cx='200' cy='230' rx='38' ry='26' fill='#fff7ea' $(St 5)/><ellipse data-k='1' cx='200' cy='216' rx='12' ry='8' fill='$K'/>" +
  (Eye 154 196) + (Eye 246 196) + (Blush 200 224 82) + (Mouth 200 228 'w') +
  "<path d='M193 240 Q200 262 207 240 Z' fill='$PINK' $(St 4)/>"))

$c = '#ffc6d3'; $l = '#ffe1e8'
$M.pig = $Ground + "<path d='M258 342 C282 330 292 352 276 358 C266 360 268 346 286 342' fill='none' $(St 6)/>" + (Body $c $l) + (Tilt (
  (Both "<path d='M112 136 C96 96 112 70 140 76 C156 82 166 96 168 108 Z' fill='$c' $(St)/>") + (Head $c) + (Shine) +
  (Eye 150 190) + (Eye 250 190) + (Blush 200 222 84) +
  "<ellipse cx='200' cy='224' rx='31' ry='22' fill='#ff9fb5' $(St 5)/><ellipse data-k='1' cx='190' cy='224' rx='4.5' ry='7' fill='$K'/><ellipse data-k='1' cx='210' cy='224' rx='4.5' ry='7' fill='$K'/>" +
  (Mouth 200 252)))

$c = '#ffd98a'; $mane = '#e8935a'
$scallops = ''
for ($i = 0; $i -lt 12; $i++) { $a = $i * [math]::PI / 6; $scallops += "<circle cx='$(Rnd (200 + 94 * [math]::Cos($a)))' cy='$(Rnd (188 + 94 * [math]::Sin($a)))' r='31' fill='$mane' $(St)/>" }
$M.lion = $Ground + (Tube 'M256 354 C312 354 322 314 312 292' $c 13) + "<circle cx='312' cy='284' r='17' fill='$mane' $(St)/>" + (Body $c '#fff1cf') + (Tilt (
  $scallops + "<circle cx='200' cy='188' r='98' fill='$mane'/>" +
  (Both "<circle cx='140' cy='116' r='22' fill='$c' $(St)/><circle data-c='1' cx='140' cy='116' r='10' fill='#ffc2d4'/>") +
  "<ellipse cx='200' cy='192' rx='82' ry='74' fill='$c' $(St)/>" + (Shine 160 146) +
  "<ellipse cx='200' cy='220' rx='30' ry='21' fill='#fff1cf' $(St 5)/><path d='M190 206 L210 206 L200 217 Z' fill='#b5654a' $(St 4)/>" +
  (Eye 162 184 11 14) + (Eye 238 184 11 14) + (Blush 200 208 62 14 9) + (Mouth 200 221 'w')))

$c = '#8fd694'; $l = '#dcf6d3'
$M.frog = $Ground + (Body $c $l) + (Tilt (
  (Head $c) + (Shine 200 112) +
  (Both "<circle cx='146' cy='106' r='38' fill='$c' $(St)/><circle cx='146' cy='108' r='24' fill='#fff' $(St 5)/>") +
  (Eye 146 110 11 13) + (Eye 254 110 11 13) + (Blush 200 204 80) +
  "<path d='M150 214 Q200 252 250 214' fill='none' $(St 6)/>"))

$c = '#b9c8e8'
$M.elephant = $Ground + (Body $c '#dfe7f7') + (Tilt (
  (Both "<path d='M112 110 C52 96 28 150 40 204 C50 246 92 254 118 232 Z' fill='$c' $(St)/><path data-c='1' d='M106 132 C68 124 54 160 60 198 C66 224 90 228 106 216 Z' fill='#ffc9d6'/>") +
  (Head $c) + (Shine) + (Eye 150 188) + (Eye 250 188) + (Blush 200 216 82) +
  "<path d='M222 240 Q232 248 241 238' fill='none' $(St 5)/>" +
  "<path d='M200 224 C202 256 190 272 166 264' fill='none' stroke='$O' stroke-width='40' stroke-linecap='round'/><path d='M200 208 C202 252 190 272 166 264' fill='none' stroke='$c' stroke-width='27' stroke-linecap='round'/>"))

$c = '#b98d6a'; $l = '#fbe8cf'
$M.owl = $Ground + (Body $c $l '#ffb347') +
  "<path data-c='1' d='M186 322 l7 7 l7 -7 M200 340 l7 7 l7 -7 M172 340 l7 7 l7 -7' fill='none' stroke='$c' stroke-width='5' stroke-linecap='round' stroke-linejoin='round'/>" + (Tilt (
  (Both "<path d='M112 132 L104 70 Q140 84 162 100 Z' fill='$c' $(St)/>") + (Head $c) +
  (Both "<circle cx='154' cy='186' r='41' fill='$l' $(St 5)/>") +
  (Eye 154 188 14 17) + (Eye 246 188 14 17) + (Blush 200 236 78) +
  "<path d='M188 214 L212 214 L200 235 Z' fill='#ffb347' $(St 5)/>"))

$c = '#5f7099'
$M.penguin = $Ground + (Body $c '#ffffff' '#ffb347') + (Tilt (
  (Head $c) + (Shine) +
  "<path d='M200 132 C170 110 122 128 122 186 C122 240 160 264 200 264 C240 264 278 240 278 186 C278 128 230 110 200 132Z' fill='#fff' $(St 5)/>" +
  (Eye 160 190) + (Eye 240 190) + (Blush 200 218 64 15 9) +
  "<ellipse cx='200' cy='216' rx='14' ry='9' fill='#ffb347' $(St 5)/>"))

$c = '#ffe07a'
$M.duck = $Ground + (Body $c '#fff3c2' '#ffa53d') + (Tilt (
  "<path d='M194 90 C186 62 202 48 214 56 C206 64 206 76 210 90' fill='$c' $(St)/>" + (Head $c) + (Shine) +
  (Eye 152 188) + (Eye 248 188) + (Blush 200 216 84) +
  "<ellipse cx='200' cy='222' rx='31' ry='16' fill='#ffa53d' $(St 5)/><path d='M177 222 Q200 231 223 222' fill='none' $(St 4)/>"))

$c = '#8ed1a5'; $sp = '#ffb36b'
$M.dino = $Ground + "<path d='M250 350 C300 358 342 342 352 300 C322 318 290 316 256 308 Z' fill='$c' $(St)/>" + (Body $c '#fff3c2') + (Tilt (
  "<path d='M150 106 L160 62 L188 94 Z' fill='$sp' $(St)/><path d='M184 92 L200 46 L218 92 Z' fill='$sp' $(St)/><path d='M214 94 L242 62 L250 106 Z' fill='$sp' $(St)/>" +
  (Head $c) + (Shine) + "<circle data-c='1' cx='262' cy='132' r='9' fill='#6fbf8c'/><circle data-c='1' cx='282' cy='160' r='6' fill='#6fbf8c'/><circle data-c='1' cx='244' cy='112' r='5' fill='#6fbf8c'/>" +
  (Face 200 198 46 'open' 20)))

$c = '#ffffff'
$M.unicorn = $Ground + "<path d='M258 342 C300 330 314 366 292 380 C276 388 262 378 262 364' fill='#c9b6ff' $(St)/>" + (Body $c '#fff0f6') + (Star 200 334 .8) + (Tilt (
  "<circle cx='104' cy='150' r='30' fill='#ffb3d1' $(St)/><circle cx='96' cy='200' r='28' fill='#c9b6ff' $(St)/><circle cx='108' cy='246' r='25' fill='#a8e0ff' $(St)/>" +
  "<path d='M286 128 L284 70 Q256 82 240 102 Z' fill='$c' $(St)/>" +
  "<path d='M186 98 L200 22 L214 98 Z' fill='#ffd966' $(St)/><path d='M193 74 L208 66 M190 88 L211 78 M196 54 L205 49' fill='none' $(St 4)/>" +
  (Head $c) + "<path d='M196 86 C230 82 258 102 264 130 C240 136 212 124 196 86Z' fill='#ffb3d1' $(St)/>" +
  (Face 200 204 44 'smile' 22)))

$c = '#a6dc8c'
$M.turtle = $Ground + "<ellipse cx='200' cy='322' rx='94' ry='66' fill='#c9966b' $(St)/>" +
  "<path data-c='1' d='M118 300 l16 12 l-10 18 M282 300 l-16 12 l10 18' fill='none' stroke='#a87a52' stroke-width='6' stroke-linecap='round' stroke-linejoin='round'/>" +
  (Body $c '#fff3c2') + "<path data-c='1' d='M200 304 V364 M170 334 H230' fill='none' stroke='#ecd9a0' stroke-width='5' stroke-linecap='round'/>" + (Tilt (
  (Head $c) + (Shine) + (Face 200 198 46 'smile' 22)))

# ---------- sea friends ----------
$M.fish = "<path d='M286 200 C330 150 360 140 372 150 C364 190 364 210 372 250 C360 260 330 250 286 200Z' fill='#ff8f6b' $(St)/>" +
  "<path d='M150 106 C160 58 222 54 242 102 Z' fill='#ff8f6b' $(St)/>" +
  "<path d='M70 200 C70 130 130 90 200 90 C262 90 300 130 300 200 C300 270 262 310 200 310 C130 310 70 270 70 200Z' fill='#ffb27a' $(St)/>" +
  "<ellipse data-c='1' cx='176' cy='268' rx='56' ry='26' fill='#ffdcb8'/>" + (Shine 130 132) +
  "<path d='M218 238 C250 234 262 258 248 274 C230 272 218 258 218 238Z' fill='#ff8f6b' $(St)/>" +
  (Face 172 192 42 'smile' 22) +
  "<circle cx='330' cy='92' r='12' fill='#d6f1ff' $(St 4)/><circle cx='352' cy='60' r='8' fill='#d6f1ff' $(St 4)/><circle cx='312' cy='58' r='6' fill='#d6f1ff' $(St 4)/>"

$c = '#8ec9f0'
$M.whale = "<path d='M350 172 C330 152 328 124 346 120 C356 120 360 132 358 142 C366 130 380 128 386 138 C390 154 372 170 350 172Z' fill='$c' $(St)/>" +
  "<path d='M50 232 C50 152 110 112 190 112 C270 112 318 152 322 216 C338 210 348 194 346 168 L356 170 C372 190 374 214 366 232 C350 270 318 302 250 312 C200 318 150 318 110 306 C74 294 50 270 50 232Z' fill='$c' $(St)/>" +
  "<path data-c='1' d='M66 264 C120 300 240 304 316 264 C290 300 220 312 180 312 C130 312 86 298 66 264Z' fill='#e3f4ff'/>" + (Shine 120 148) +
  (Face 168 214 42 'smile' 22) +
  "<path d='M190 110 C190 84 176 70 158 66 M190 110 C192 82 208 70 226 66' fill='none' stroke='$O' stroke-width='6' stroke-linecap='round'/>" + (Heart 192 44 .9)

$c = '#c9a6f5'
$tent = @('M140 262 C122 318 92 330 70 308', 'M260 262 C278 318 308 330 330 308', 'M166 280 C160 338 132 366 104 356', 'M234 280 C240 338 268 366 296 356', 'M190 286 C186 336 178 360 160 378', 'M210 286 C214 336 222 360 240 378')
$tO = ''; $tC = ''
foreach ($d in $tent) { $tO += "<path d='$d' fill='none' stroke='$O' stroke-width='36' stroke-linecap='round'/>"; $tC += "<path d='$d' fill='none' stroke='$c' stroke-width='22' stroke-linecap='round'/>" }
$M.octopus = $tO + $tC + (Tilt ((Head $c) + (Shine) +
  "<circle data-c='1' cx='262' cy='128' r='8' fill='#e3ccff'/><circle data-c='1' cx='280' cy='156' r='5' fill='#e3ccff'/>" +
  (Face 200 204 46 'open' 20)) -4)

# ---------- garden friends ----------
$c = '#ffe7a8'
$M.snail = $Ground + "<path d='M96 202 C92 178 84 162 76 152 M122 200 C126 176 134 162 142 154' fill='none' $(St 6)/><circle cx='74' cy='148' r='10' fill='$c' $(St 5)/><circle cx='144' cy='150' r='10' fill='$c' $(St 5)/>" +
  "<path d='M40 322 C40 298 60 292 78 298 C84 252 70 216 92 198 C116 182 140 200 138 228 C136 264 134 302 150 322 L340 322 C366 322 372 350 346 354 L80 354 C54 354 40 342 40 322Z' fill='$c' $(St)/>" +
  "<circle cx='236' cy='224' r='100' fill='#ffc98f' $(St)/><ellipse data-c='1' cx='190' cy='160' rx='26' ry='11' fill='#fff' opacity='.45' transform='rotate(-35 190 160)'/>" +
  "<path d='M184 224 a52 52 0 1 1 52 52 a34 34 0 0 1 -34 -34 a18 18 0 1 1 18 18' fill='none' $(St 6)/>" +
  (Eye 96 240 8 10) + (Eye 124 240 8 10) + (Blush 110 256 26 9 6) + "<path d='M103 258 Q110 266 117 258' fill='none' $(St 4)/>"

$M.butterfly = (Both "<path d='M196 192 C150 92 60 72 44 132 C30 192 110 232 196 216 Z' fill='#ffb3d1' $(St)/><path d='M196 216 C120 222 70 262 90 312 C112 358 180 322 198 242 Z' fill='#c9b6ff' $(St)/><circle data-c='1' cx='100' cy='152' r='22' fill='#fff' opacity='.7'/><circle data-c='1' cx='134' cy='290' r='15' fill='#fff' opacity='.7'/><circle data-c='1' cx='150' cy='186' r='9' fill='#ffe07a'/>") +
  "<ellipse cx='200' cy='264' rx='22' ry='56' fill='#ffe07a' $(St)/><path data-c='1' d='M182 254 H218 M182 280 H218' fill='none' stroke='#f5c84c' stroke-width='6' stroke-linecap='round'/>" +
  (Both "<path d='M188 134 C176 102 160 88 146 88' fill='none' $(St 6)/><circle cx='142' cy='88' r='9' fill='$PINK' $(St 5)/>") +
  "<circle cx='200' cy='174' r='48' fill='#ffe07a' $(St)/>" + (Eye 183 172 9 11) + (Eye 217 172 9 11) + (Blush 200 190 30 9 6) + "<path d='M192 190 Q200 199 208 190' fill='none' $(St 4)/>"

# ---------- things that go / yummy / home ----------
$c = '#bfe3f7'; $d = '#8fc7ea'
$M.robot = $Ground + (Both "<rect x='150' y='366' width='38' height='24' rx='11' fill='$d' $(St)/>") +
  (Tube 'M140 300 C112 300 100 320 104 342' $d) + (Tube 'M260 296 C292 290 304 268 300 246' $d) +
  "<rect x='138' y='266' width='124' height='108' rx='34' fill='$c' $(St)/>" + (Heart 200 322 1.1) + (Tilt (
  (Both "<rect x='72' y='158' width='28' height='48' rx='12' fill='$d' $(St)/>") +
  "<path d='M200 96 V62' fill='none' $(St)/><circle cx='200' cy='50' r='15' fill='$PINK' $(St)/>" +
  "<rect x='96' y='96' width='208' height='176' rx='50' fill='$c' $(St)/>" + (Shine 150 118) +
  "<rect x='122' y='130' width='156' height='114' rx='36' fill='#ffffff' $(St 5)/>" +
  (Eye 164 180) + (Eye 236 180) + (Blush 200 206 56 13 8) + (Mouth 200 202)) -4)

$M.rocket = (Star 64 84 .9) + (Star 340 300 .7) + "<circle cx='330' cy='96' r='7' fill='#ffe07a' $(St 4)/>" + "<g transform='rotate(16 200 210)'>" +
  "<path d='M168 316 C160 354 184 370 200 392 C216 370 240 354 232 316 Z' fill='#ffb347' $(St)/><path data-c='1' d='M184 320 C180 342 192 354 200 366 C208 354 220 342 216 320 Z' fill='#ffe07a'/>" +
  (Both "<path d='M142 240 C102 262 94 300 100 334 C122 322 142 312 154 300 Z' fill='#ff7a7a' $(St)/>") +
  "<path d='M200 40 C258 86 270 190 250 318 L150 318 C130 190 142 86 200 40Z' fill='#ffffff' $(St)/>" +
  "<path d='M200 40 C232 66 250 102 256 138 L144 138 C150 102 168 66 200 40Z' fill='#ff7a7a' $(St)/>" +
  "<path data-c='1' d='M152 292 H248 L246 312 H154 Z' fill='#bfe3f7'/>" +
  (Face 200 204 34 'smile' 22 12 15) + "</g>"

$c = '#ff9c9c'
$M.car = $Ground + (Both "<circle cx='112' cy='326' r='34' fill='#6a5763' $(St)/><circle cx='112' cy='326' r='14' fill='#ffffff' $(St 5)/>") +
  "<path d='M40 290 C40 250 60 236 96 232 C112 180 140 150 200 150 C262 150 288 180 304 232 C344 236 360 250 360 290 C360 314 348 324 330 324 L70 324 C52 324 40 314 40 290Z' fill='$c' $(St)/>" +
  "<path d='M124 232 C134 196 158 176 200 176 C244 176 266 196 276 232 Z' fill='#e3f4ff' $(St 5)/>" + (Shine 96 256) +
  (Eye 172 210 11 13) + (Eye 228 210 11 13) + (Blush 200 276 78) + (Mouth 200 264) +
  (Both "<circle cx='74' cy='276' r='12' fill='#ffe07a' $(St 5)/>") +
  (Both "<circle cx='112' cy='326' r='34' fill='#6a5763' $(St)/><circle cx='112' cy='326' r='14' fill='#ffffff' $(St 5)/>") +
  (Heart 352 196 .8) + (Heart 376 160 .5)

$M.cupcake = $Ground + "<path d='M110 250 L134 372 C136 382 144 386 154 386 L246 386 C256 386 264 382 266 372 L290 250 Z' fill='#ffd3df' $(St)/>" +
  "<path data-c='1' d='M146 262 L158 378 M254 262 L242 378' fill='none' stroke='#ff9fb5' stroke-width='6' stroke-linecap='round'/>" +
  (Face 200 306 34 'smile' 20 11 14) +
  "<path d='M92 252 C70 220 100 192 130 200 C120 162 160 138 190 152 C196 122 240 120 248 152 C280 142 306 172 290 202 C322 206 326 242 304 254 C250 264 150 264 92 252Z' fill='#fff7ea' $(St)/>" +
  "<path data-c='1' d='M140 214 l12 -6 M186 178 l10 8 M236 196 l12 -4 M270 228 l-10 -8 M118 236 l8 8 M212 232 l10 6' fill='none' stroke='#8ec9f0' stroke-width='7' stroke-linecap='round'/>" +
  "<path data-c='1' d='M162 190 l8 8 M256 172 l-6 10 M176 236 l12 -2 M246 236 l8 -8' fill='none' stroke='$PINK' stroke-width='7' stroke-linecap='round'/>" +
  "<path d='M214 96 C216 74 228 62 242 58' fill='none' $(St 5)/><circle cx='212' cy='116' r='25' fill='#ff6b7f' $(St)/><ellipse data-c='1' cx='203' cy='107' rx='8' ry='5' fill='#fff' opacity='.6' transform='rotate(-30 203 107)'/>"

$M.house = $Ground + "<rect x='246' y='92' width='38' height='76' rx='9' fill='#e9a37a' $(St)/>" + (Heart 266 62 .8) + (Heart 292 34 .5) +
  "<path d='M200 104 L304 196 L304 350 C304 366 294 376 278 376 L122 376 C106 376 96 366 96 350 L96 196 Z' fill='#fff3c2' $(St)/>" +
  "<circle cx='200' cy='178' r='19' fill='#bfe3f7' $(St 5)/><path d='M200 160 V196 M182 178 H218' fill='none' $(St 4)/>" +
  "<path d='M60 206 C56 198 60 190 68 184 L186 86 C194 80 206 80 214 86 L332 184 C340 190 344 198 340 206 C334 216 322 216 314 210 L200 118 L86 210 C78 216 66 216 60 206Z' fill='#ff7a7a' $(St)/>" +
  (Face 200 268 44 'smile' 22) +
  "<path data-c='1' d='M104 372 q8 -18 16 0 q8 -18 16 0 M264 372 q8 -18 16 0 q8 -18 16 0' fill='none' stroke='#8fd694' stroke-width='6' stroke-linecap='round' stroke-linejoin='round'/>"

# ---------- write files ----------
$enc = New-Object System.Text.UTF8Encoding $false
foreach ($name in $M.Keys) {
  $svg = "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 400 400'>" + $M[$name] + "</svg>"
  [IO.File]::WriteAllText((Join-Path $outColor "$name.svg"), $svg, $enc)
  # colouring-page version: drop colour-only details, white fills, keep outlines and eyes
  $line = [regex]::Replace($svg, "<[^<>]*data-c='1'[^<>]*/>", '')
  $line = [regex]::Replace($line, "<[^<>]+>", {
      param($m) $t = $m.Value
      if ($t -match "data-k='1'") { return $t }
      $t = [regex]::Replace($t, "fill='#[0-9a-fA-F]{3,6}'", "fill='#fff'")
      [regex]::Replace($t, "stroke='(#[0-9a-fA-F]{3,6})'", { param($s) if ($s.Groups[1].Value -eq $O) { $s.Value } else { "stroke='#fff'" } })
    })
  $line = $line -replace " data-k='1'", ''
  [IO.File]::WriteAllText((Join-Path $outLine "$name.svg"), $line, $enc)
}
"Built $($M.Count) mascots"
