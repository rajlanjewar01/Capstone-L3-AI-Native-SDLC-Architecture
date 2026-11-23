# Protocol transcript (scripted client, NOT an LLM)

Real stdio subprocess per site (`KESTREL_SITE` in the environment). Date of data: 2026-04-08.

## Session bound to LEEDS-01

Tools published (11): search_products, list_dock_slots, list_exceptions, book_dock_slot, move_stock, raise_exception, close_exception, reopen_exception, prepare_stock_adjustment, prepare_dock_cancellation, confirm_action

### Ops: "How many pallet wrap have we got?"  (two products match -> agent must ask, not guess)

`search_products` {"query": "pallet wrap"}  ->  isError=False

```json
{
  "ok": true,
  "site": "LEEDS-01",
  "data": {
    "query": "pallet wrap",
    "match_type": "exact_terms",
    "resolution": "multiple_matches",
    "match_count": 2,
    "candidates": [
      {
        "sku": "SKU-8801",
        "description": "Pallet wrap, 500mm clear",
        "bin": "A-12-3",
        "quantity": 240,
        "unit": "each",
        "in_stock": true
      },
      {
        "sku": "SKU-8802",
        "description": "Pallet wrap, 500mm black",
        "bin": "A-12-4",
        "quantity": 180,
        "unit": "each",
        "in_stock": true
      }
    ],
    "disambiguate_by": [
      "clear",
      "black"
    ]
  },
  "guidance": "More than one product matches. Do NOT pick one. Ask the user which they mean using disambiguate_by (e.g. 'clear or black?'), or report each item separately if they asked about all of them."
}
```

### Ops: "The clear one."  (agent re-uses the SKU from the previous result)

`search_products` {"query": "clear pallet wrap"}  ->  isError=False

```json
{
  "ok": true,
  "site": "LEEDS-01",
  "data": {
    "query": "clear pallet wrap",
    "match_type": "exact_terms",
    "resolution": "single_match",
    "match_count": 1,
    "candidates": [
      {
        "sku": "SKU-8801",
        "description": "Pallet wrap, 500mm clear",
        "bin": "A-12-3",
        "quantity": 240,
        "unit": "each",
        "in_stock": true
      }
    ],
    "disambiguate_by": []
  },
  "guidance": "Exactly one product at this site matches. You can answer directly; state the quantity with its unit (and say out of stock if quantity is 0)."
}
```

### Ops: "Any void fill?"  (only one match at Leeds -> answer directly, no nagging)

`search_products` {"query": "void fill"}  ->  isError=False

```json
{
  "ok": true,
  "site": "LEEDS-01",
  "data": {
    "query": "void fill",
    "match_type": "exact_terms",
    "resolution": "single_match",
    "match_count": 1,
    "candidates": [
      {
        "sku": "SKU-8811",
        "description": "Void fill, air pillow",
        "bin": "A-19-6",
        "quantity": 420,
        "unit": "box",
        "in_stock": true
      }
    ],
    "disambiguate_by": []
  },
  "guidance": "Exactly one product at this site matches. You can answer directly; state the quantity with its unit (and say out of stock if quantity is 0)."
}
```

### Ops: "Book the 8 o'clock dock for Acme."  (already taken -> actionable error)

`book_dock_slot` {"date": "2026-04-08", "slot": "08:00", "carrier": "Acme Ltd"}  ->  isError=True

```json
{
  "ok": false,
  "error": {
    "code": "SLOT_ALREADY_BOOKED",
    "message": "LEEDS-01 08:00 on 2026-04-08 is already booked by Northbound Freight.",
    "retryable": false,
    "parameter": "slot",
    "received": "08:00",
    "valid_values": [
      "06:00",
      "10:00",
      "14:00",
      "16:00"
    ],
    "how_to_fix": "Choose one of the free slots in valid_values, or cancel the existing booking with prepare_dock_cancellation first. Ask the user which they prefer.",
    "suggested_call": {
      "tool": "book_dock_slot",
      "arguments": {
        "date": "2026-04-08",
        "slot": "06:00",
        "carrier": "Acme Ltd"
      }
    },
    "problems": null,
    "booked_by": "Northbound Freight"
  }
}
```

### Agent self-corrects using the error's suggested_call (first free slot)

`book_dock_slot` {"date": "2026-04-08", "slot": "06:00", "carrier": "Acme Ltd"}  ->  isError=False

```json
{
  "ok": true,
  "site": "LEEDS-01",
  "data": {
    "date": "2026-04-08",
    "slot": "06:00",
    "carrier": "Acme Ltd",
    "status": "booked"
  },
  "guidance": "Booked. To undo, use prepare_dock_cancellation for 06:00 on 2026-04-08."
}
```

### Ops: "The black wrap count is actually 150."  (irreversible -> preview only, nothing changes)

`prepare_stock_adjustment` {"sku": "SKU-8802", "counted_quantity": 150, "reason": "RECOUNT"}  ->  isError=False

```json
{
  "ok": true,
  "site": "LEEDS-01",
  "data": {
    "preview": {
      "summary": "Change SKU-8802 (Pallet wrap, 500mm black) at LEEDS-01 from 180 to 150 each (-30). Reason: RECOUNT. This feeds the month-end count and cannot be undone.",
      "sku": "SKU-8802",
      "description": "Pallet wrap, 500mm black",
      "unit": "each",
      "current_quantity": 180,
      "counted_quantity": 150,
      "delta": -30,
      "reason": "RECOUNT",
      "warnings": []
    },
    "confirmation_token": "CONF-cwKrvSmK7_jwpnPG",
    "expires_in_seconds": 300
  },
  "guidance": "NOTHING HAS CHANGED YET. Show the preview to the user and wait for an explicit yes, then call confirm_action with the token."
}
```

### Ops: "What does Reading have of corner protector?"  (cross-site: refused as not found)

`search_products` {"query": "corner protector"}  ->  isError=False

```json
{
  "ok": true,
  "site": "LEEDS-01",
  "data": {
    "query": "corner protector",
    "match_type": "none",
    "resolution": "no_match",
    "match_count": 0,
    "candidates": [],
    "disambiguate_by": []
  },
  "guidance": "Nothing at this site matches. Ask the user to rephrase or give another word from the product name. Do not guess, and do not suggest the item is stocked elsewhere."
}
```

### Agent tries SKU-8805 directly (a Reading SKU)

`move_stock` {"sku": "SKU-8805", "to_bin": "A-01-1"}  ->  isError=True

```json
{
  "ok": false,
  "error": {
    "code": "SKU_NOT_FOUND",
    "message": "No product SKU-8805 at LEEDS-01.",
    "retryable": false,
    "parameter": "sku",
    "received": "SKU-8805",
    "valid_values": null,
    "how_to_fix": "Use search_products with the product's name to find the right SKU at this site. Only this site's stock can be accessed.",
    "suggested_call": {
      "tool": "search_products",
      "arguments": {
        "query": "<product words>"
      }
    },
    "problems": null
  }
}
```

### Agent tries to pass a site parameter

`list_dock_slots` {"date": "2026-04-08", "site": "READING-02"}  ->  isError=True

```json
{
  "ok": false,
  "error": {
    "code": "INVALID_ARGUMENTS",
    "message": "The call to list_dock_slots was rejected: site: 'site' is not a parameter. This session is fixed to LEEDS-01 and every tool only ever acts on that site.",
    "retryable": false,
    "parameter": "site",
    "received": "READING-02",
    "valid_values": null,
    "how_to_fix": "Remove `site` and call list_dock_slots again: this session is fixed to LEEDS-01, and no tool can act on another site. Correct site and call list_dock_slots again. Each entry in `problems` says what is wrong, what is allowed, and gives an example.",
    "suggested_call": null,
    "problems": [
      {
        "parameter": "site",
        "problem": "'site' is not a parameter. This session is fixed to LEEDS-01 and every tool only ever acts on that site.",
        "received": "READING-02",
        "expected": "remove it",
        "valid_values": null,
        "example": null
      }
    ]
  }
}
```

### Deliberately invalid argument (slot 25:00, wrong date format)

`book_dock_slot` {"date": "08/04/2026", "slot": "25:00", "carrier": "Acme Ltd"}  ->  isError=True

```json
{
  "ok": false,
  "error": {
    "code": "INVALID_ARGUMENTS",
    "message": "The call to book_dock_slot was rejected: date: wrong format; slot: not an allowed value.",
    "retryable": false,
    "parameter": "date",
    "received": "08/04/2026",
    "valid_values": null,
    "how_to_fix": "Correct date, slot and call book_dock_slot again. Each entry in `problems` says what is wrong, what is allowed, and gives an example.",
    "suggested_call": null,
    "problems": [
      {
        "parameter": "date",
        "problem": "wrong format",
        "received": "08/04/2026",
        "expected": "text matching ^\\d{4}-\\d{2}-\\d{2}$",
        "valid_values": null,
        "example": "2026-04-08"
      },
      {
        "parameter": "slot",
        "problem": "not an allowed value",
        "received": "25:00",
        "expected": "one of: 06:00, 08:00, 10:00, 12:00, 14:00, 16:00",
        "valid_values": [
          "06:00",
          "08:00",
          "10:00",
          "12:00",
          "14:00",
          "16:00"
        ],
        "example": "10:00"
      }
    ]
  }
}
```

### Quantity is still 180 after the preview (nothing changed yet)

```json
{
  "ok": true,
  "site": "LEEDS-01",
  "data": {
    "query": "SKU-8802",
    "match_type": "exact_terms",
    "resolution": "single_match",
    "match_count": 1,
    "candidates": [
      {
        "sku": "SKU-8802",
        "description": "Pallet wrap, 500mm black",
        "bin": "A-12-4",
        "quantity": 180,
        "unit": "each",
        "in_stock": true
      }
    ],
    "disambiguate_by": []
  },
  "guidance": "Exactly one product at this site matches. You can answer directly; state the quantity with its unit (and say out of stock if quantity is 0)."
}
```

### User says yes -> confirm_action

`confirm_action` -> isError=False

```json
{
  "ok": true,
  "site": "LEEDS-01",
  "data": {
    "action": "stock_adjustment",
    "result": {
      "ledger_id": "LED-0001",
      "site": "LEEDS-01",
      "sku": "SKU-8802",
      "before": 180,
      "after": 150,
      "delta": -30,
      "reason": "RECOUNT"
    }
  },
  "guidance": "Done. Tell the user exactly what was changed."
}
```

### Reusing the same token is refused (single use)

`confirm_action` -> isError=True

```json
{
  "ok": false,
  "error": {
    "code": "CONFIRMATION_INVALID",
    "message": "That confirmation token is unknown, already used, or was not issued to this site.",
    "retryable": false,
    "parameter": "confirmation_token",
    "received": "CONF-cwKrvSmK7_jwpnPG",
    "valid_values": null,
    "how_to_fix": "Run the prepare_* tool again to get a fresh preview and token, show it to the user, then call confirm_action.",
    "suggested_call": null,
    "problems": null
  }
}
```


## Session bound to GLASGOW-03

Tools published (11): search_products, list_dock_slots, list_exceptions, book_dock_slot, move_stock, raise_exception, close_exception, reopen_exception, prepare_stock_adjustment, prepare_dock_cancellation, confirm_action

### Ops (Glasgow): "How many 600 shrink film?"  (out of stock is an answer, not an error)

`search_products` {"query": "600mm shrink film"}  ->  isError=False

```json
{
  "ok": true,
  "site": "GLASGOW-03",
  "data": {
    "query": "600mm shrink film",
    "match_type": "exact_terms",
    "resolution": "single_match",
    "match_count": 1,
    "candidates": [
      {
        "sku": "SKU-8809",
        "description": "Shrink film, 600mm",
        "bin": "C-08-2",
        "quantity": 0,
        "unit": "roll",
        "in_stock": false
      }
    ],
    "disambiguate_by": []
  },
  "guidance": "Exactly one product at this site matches. You can answer directly; state the quantity with its unit (and say out of stock if quantity is 0)."
}
```

