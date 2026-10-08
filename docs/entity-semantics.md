# Entity semantics and upgrade notes

Gas: OFF means closed, ON means open. The entity adds valve_state and state_meaning
attributes. Only OFF closes the valve; ON raises HomeAssistantError because remote
opening is not verified. State changes wait for received feedback. Unknown codes
remain unknown. Review gas automation conditions: the legacy integration used ON
for closed and allowed ON to send closure bytes.

Elevator: replace switch actions with button.press against the actual newly created
button entity ID. The old switch registry entry is not deleted automatically; check
and disable the obsolete entity through Home Assistant. Existing call bytes are
preserved, but physical command success and direction selection remain unverified.
No floor or arrival sensor is introduced from incomplete evidence.

The climate constructor initializes received attributes before HA registration.
Packet logging remains optional. These source changes are committed on local
`main`; source branch state does not prove HA deployment. Verify deployed code
and runtime behavior separately through HA-MCP before any deployment or control.

Offline tests do not certify live HA compatibility. Known follow-ups include
length-driven stream framing, gateway task cancellation, connection availability,
transport failure propagation, entry-scoped unique IDs/dispatcher signals, and fan
speed/preset mapping. Do not infer meter data from unknown frames.
