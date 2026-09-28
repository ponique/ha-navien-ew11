# EW11 protocol evidence

This map summarizes passive capture and ordinary wallpad use in one installation.
It is not a protocol specification for every Navien/Kyungdong model. Raw household
captures, timestamps, addresses and credentials are deliberately excluded.

`VERIFIED_PACKET` means a received frame was correlated with the user's wallpad
observation. `VERIFIED_RUNTIME` means Home Assistant was checked through a read-only
connection. `VERIFIED_CODE` refers to the checked source. Unobserved behavior stays
`NOT_VERIFIED`; a plausible interpretation is `STRONGLY_INDICATED`.

## Framing

Observed frames use `F7 device sub command length payload XOR ADD`.
Length is the number of payload bytes; XOR covers bytes before the two checksums;
ADD is the low byte of the sum through XOR. Capture reconstruction and independent
checksum/length checks passed in the completed experiments. TCP chunks can contain
partial or multiple frames, so searching arbitrary chunk substrings is insufficient.

In `make_cmd`, the first element of its local `payload` list is actually the wire
length byte. For example, `[0x01, 0x00]` produces length 1 and payload `00`, not a
two-byte payload. Compare the complete generated frame when evaluating commands.

## Gas (device 0x12)

| Command | Payload | Evidence |
|---|---|---|
| RX 0x81 | `00 01` | Wallpad open display before manual closure; physical open position was not independently inspected. |
| RX 0x41 | `00` | Correlated with one user-initiated closure. Same complete bytes as the existing gas command builder. |
| RX 0xC1 | `00 02` | Closure response candidate, STRONGLY_INDICATED. |
| RX 0x81 | `00 02` | VERIFIED_PACKET: wallpad closed display and user-confirmed physically closed valve. |
| RX 0x81 | `00 04` | Legacy closed value recognized by source and third-party material; not physically verified in this installation. |

The current switch displays **OFF = closed, ON = open**. The legacy switch modeled
closed as on; existing automation state conditions must be reviewed when upgrading.
Recognizing closed code `02` preserves the legacy `04` variant. Unknown status codes
are represented as unknown, not inferred as open. Only the `off` closure action is
supported. Opening requests raise an error without transmission; no opening command
has been verified. This does not establish remote physical control success. User-
reported electrical cutoff accompanied closure, but its cause and scope remain
NOT_VERIFIED.

## Thermostat (device 0x36)

| Command / field | Evidence |
|---|---|
| RX 0x81, payload from offset 5 | VERIFIED_PACKET for the first room: pairs are set/current temperature; ordinary integer values agreed with the wallpad and HA. |
| RX sub 0x11 / cmd 0x44 | VERIFIED_PACKET: first room set-temperature change and restoration, one-byte temperature payload. |
| RX sub 0x11 / cmd 0x45, payload `01` | Correlated with first room away selection. |
| RX sub 0x11 / cmd 0x43, payload `01` | Correlated with restoring normal heating. |
| RX 0x81, payload offsets 1 and 2 | VERIFIED_PACKET for bit 0: normal heating clears away and sets heating; away clears heating and sets away. Other room mode bits stayed unchanged. |
| RX 0xC4 / 0xC5 / 0xC3 | Full-state reply candidates following the corresponding requests. |

VERIFIED_RUNTIME: the tested room changed `heat/none -> off/away -> heat/none`.
The wallpad offers heating/away, not an independent off control. Away is not proven
to mean physically shutting down the boiler. Actual heat output, all room-to-index
mappings, fractional temperatures, an independent off operation, and HA-generated
command execution remain NOT_VERIFIED. A value edited without pressing Apply did
not change the bus or HA; this was not a parser failure.

## Elevator (device 0x33)

| Command | Evidence |
|---|---|
| RX 0x44, one-byte payload | VERIFIED_PACKET for user-observed floor values; packed BCD interpretation is STRONGLY_INDICATED. Do not use ordinary hexadecimal-to-integer conversion as floor decoding. |
| RX 0xC4, `00 44 00` | Repeated following floor messages; reply role STRONGLY_INDICATED. |
| RX 0x57, empty payload | STRONGLY_INDICATED arrival-related event: observed in two trials with user-confirmed arrivals. Exact door/alarm semantics unverified. |
| RX 0x81, `00 44 00` | Constant at baseline and around calls; no evidence that this boolean represents a live call or arrival. HA remained on. |
| RX 0x51 | Periodic payload with changing date/time candidates; remaining meaning NOT_VERIFIED. |

Three calls were made in normal use. The last capture ended before arrival and
cannot count as a third observed arrival frame. Requested boarding direction is
different from current car motion. Basement values, special displays, direction
bits and the full call-command protocol are NOT_VERIFIED. Existing code ignores
0x44/0xC4/0x57; floor and arrival should be modeled separately from a call command.

## Metering and other traffic

Opening the wall-mounted daily electricity graph did not introduce a new device or
command in the captured EW11 path. Two displayed kWh readings had no match in the
tested fixed-point integer, packed BCD or ASCII representations. This does not
prove absence on every RS485 bus, nor rule out other encoding or IP/server paths.
Gas/water/hot-water/heating consumption screens were not tested. No metering sensor
should be activated from a guessed interpretation of the periodic 0x33/0x51 frame.

Baseline also contained lighting 0x0E/0x81 and ventilation 0x32/0x0F. The latter
does not prove that a physical ventilation unit or HA fan entity exists. Existing
poll-like 0x01 messages are observations, not a complete inferred specification.

## Entity control model

Elevator calls use a stateless button and the existing `43/10` command builder.
Repeated presses are not gated by the periodic `81` boolean. Generated bytes are
code-verified; a successful Home Assistant press does not prove physical arrival.
The old elevator switch is no longer created, but its registry entry/dashboard
references may remain and need migration after inspecting the actual new button ID.
