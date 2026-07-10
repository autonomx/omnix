# TP-Link Kasa smart-plug integration

Omnix can use Live Agent and Hermes to plan TP-Link Kasa smart-plug requests while keeping device discovery, approval, execution, verification, and audit inside Omnix.

## Safety model

- `discover_devices` and `get_state` are read-only and may run immediately.
- `turn_on` and `turn_off` always require a separate explicit confirmation turn.
- Hermes only proposes the Kasa action. It never talks directly to the plug.
- Omnix validates the request against the Assistant Tools registry and approval gate.
- Omnix executes the approved action locally with `python-kasa`.
- Omnix refreshes the device after the command and reports success only when the resulting state is verified.
- Each reviewed or executed request is recorded in the Assistant Tools ledger without storing Kasa credentials.
- A proposal can be consumed only once. Repeated `confirm` messages cannot replay it.
- There are no schedules, background actions, or autonomous plug changes in this phase.

Do not connect medical devices, heaters, computers, networking equipment, refrigeration, or other safety-critical loads during initial testing.

## Install the runtime dependency

From the repository root, install `python-kasa` into the application environment:

```bat
C:\Users\unx47\miniconda3\envs\rpg-flux\python.exe -m pip install "python-kasa>=0.10.2,<1.0"
```

The dependency is also included in `requirements.txt` for a complete environment install.

## Configuration

`start_all.bat` enables Kasa support for the local pilot and exports these variables to Omnix:

```bat
set OMNIX_KASA_ENABLED=1
set OMNIX_KASA_DISCOVERY_TARGET=255.255.255.255
set OMNIX_KASA_TIMEOUT_SECONDS=4
```

When only one Kasa device is present, Omnix can discover and select it automatically. Direct host configuration is recommended for repeatable tests:

```bat
set OMNIX_KASA_DEVICE_HOST=192.168.1.42
set OMNIX_KASA_DEVICE_ALIAS=Desk Plug
start_all.bat
```

Use the actual address and alias shown by the Kasa app or discovery output. A DHCP reservation is recommended if a direct host is configured.

Some device or firmware combinations require the TP-Link account used to provision the device:

```bat
set KASA_USERNAME=your-account-email
set KASA_PASSWORD=your-account-password
start_all.bat
```

These values stay in the process environment. They are not written into Chat messages, memory, the tool ledger, or diagnostics.

## Live-call tests

Start with read-only operations:

1. Say **“Find my Kasa devices.”**
2. Say **“Is the Kasa desk plug on?”**

Then test a reviewed write:

1. Say **“Turn off the Kasa desk plug.”**
2. Omnix should describe the proposed action and ask for confirmation.
3. Say **“confirm.”**
4. Omnix should execute locally, refresh the plug, and report the verified state.

Test rejection separately:

1. Say **“Turn on the Kasa desk plug.”**
2. Say **“cancel.”**
3. Omnix should close the pending proposal without changing the plug.

## Multiple devices

When discovery finds multiple devices, specify the configured alias in the request. For example:

- “Is the desk plug on?”
- “Turn off the bedroom plug.”

If a target does not uniquely match an alias, host, or device ID, Omnix refuses the action and returns the available device aliases rather than guessing.

## Troubleshooting

### `python-kasa` is not installed

Run the installation command above in the `rpg-flux` environment and restart `start_all.bat`.

### No devices discovered

- Confirm the computer and plug are on the same LAN or VLAN.
- Disable VPN routing for the local test.
- Verify that local broadcast traffic is permitted.
- Configure `OMNIX_KASA_DEVICE_HOST` to bypass broadcast discovery.

### Authentication failure

Set `KASA_USERNAME` and `KASA_PASSWORD` to the TP-Link account used when the device was provisioned, then restart Omnix.

### Multiple devices found

Set `OMNIX_KASA_DEVICE_ALIAS` or use the device alias in the spoken request. Omnix intentionally refuses ambiguous write actions.

### Confirmation does not execute

The confirmation must immediately follow an unconsumed Kasa write proposal in the same Chat session. Supported approval phrases include `confirm`, `yes`, `go ahead`, and `do it`. `cancel`, `reject`, or `never mind` closes the proposal without execution.
