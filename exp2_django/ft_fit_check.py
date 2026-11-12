"""LoRA Step 0: does a QLoRA step on the 8B fit in 12 GB at 4096 tokens? (no project data used)

    python ft_fit_check.py --model <local weights dir> [--steps 3] [--head-dtype bf16] [--full-logits]

Runs in the separate training env only. Settings follow the planned rule (r=16, alpha=32,
dropout 0.05, 4-bit, max length 4096). The input is synthetic, always exactly 4096 tokens, the
worst case. Reports peak VRAM. Ollama must be idle (other models unloaded) for a fair number.

Loss is on the answer tokens only, so logits are computed only there (logits_to_keep = answer + 1);
--full-logits restores the first check (d4bf94f, 17.48 GiB). A short run first confirms both give the
same loss. --head-dtype bf16 undoes peft's fp32 cast of the embedding and output head (frozen, untied) and runs the
forward pass under bf16 autocast, because the fp32 LoRA and norm layers otherwise hand fp32 to the bf16 head.
--mem-fraction caps PyTorch below the card size, so going over is a clean out-of-memory error and not a
spill past the card (the first check's follow-up run ended in a driver error).
Every run appends a row to results/ft_fit_check.jsonl.
"""
import argparse
import json
import subprocess
import time

import torch
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

RESULTS = "results/ft_fit_check.jsonl"


def git_commit():
    sha = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"], text=True)
    return sha + ("-dirty" if dirty.strip() else "")


def gib(n):
    return round(n / 2**30, 2)


def forward(model, ids, answer, full_logits, autocast=False):
    """Loss on the last `answer` tokens."""
    labels = ids.clone()
    labels[:, :-answer] = -100
    with torch.autocast("cuda", dtype=torch.bfloat16, enabled=autocast):
        if full_logits:
            return model(input_ids=ids, labels=labels).loss
        keep = answer + 1             # the logit before the first answer token predicts it
        return model(input_ids=ids, labels=labels[:, -keep:], logits_to_keep=keep).loss


def same_loss(model, ids, answer, autocast):
    with torch.no_grad():
        torch.manual_seed(42)         # same LoRA dropout mask in both passes
        full = forward(model, ids, answer, True, autocast).item()
        torch.manual_seed(42)
        kept = forward(model, ids, answer, False, autocast).item()
    print(f"loss check at {ids.shape[1]} tokens: full {full:.6f}, kept {kept:.6f}", flush=True)
    assert abs(full - kept) < 1e-3, (full, kept)
    return {"full": round(full, 6), "kept": round(kept, 6), "length": ids.shape[1]}


def main(a):
    device = torch.cuda.get_device_properties(0)
    torch.cuda.set_per_process_memory_fraction(a.mem_fraction, 0)
    tok = AutoTokenizer.from_pretrained(a.model)
    bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True,
                             bnb_4bit_compute_dtype=torch.bfloat16)
    model = AutoModelForCausalLM.from_pretrained(a.model, quantization_config=bnb, device_map={"": 0})
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
    model = get_peft_model(model, LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05, task_type="CAUSAL_LM",
                                             target_modules=["q_proj", "k_proj", "v_proj", "o_proj"]))
    model.print_trainable_parameters()
    if a.head_dtype == "bf16":
        model.get_input_embeddings().to(torch.bfloat16)
        model.get_output_embeddings().to(torch.bfloat16)
        torch.cuda.empty_cache()
    model.config.use_cache = False
    model.train()                     # checkpointing only runs in train mode
    opt = torch.optim.AdamW((p for p in model.parameters() if p.requires_grad), lr=2e-4)
    full_ids = tok("Why was this change made? " * 2000, return_tensors="pt").input_ids
    ids = full_ids[:, :a.length].cuda()
    assert ids.shape[1] == a.length, ids.shape
    row = {"length": a.length, "answer": a.answer, "steps": a.steps, "head_dtype": a.head_dtype,
           "full_logits": a.full_logits, "mem_fraction": a.mem_fraction, "cap_gib": gib(device.total_memory * a.mem_fraction),
           "gpu_total_gib": gib(device.total_memory), "after_load_gib": gib(torch.cuda.memory_allocated()),
           "git_commit": git_commit(), "completed_steps": 0, "out_of_memory": False}
    print(f"after load {row['after_load_gib']} GiB; cap {row['cap_gib']} GiB", flush=True)
    if not a.full_logits:
        row["loss_check"] = same_loss(model, ids[:, :256], a.answer, a.head_dtype == "bf16")
    torch.cuda.reset_peak_memory_stats()
    t0 = time.time()
    try:
        for step in range(a.steps):
            loss = forward(model, ids, a.answer, a.full_logits, a.head_dtype == "bf16")
            loss.backward()
            opt.step()
            opt.zero_grad()
            row["completed_steps"] = step + 1
            print(f"step {step} loss {loss.item():.3f} peak {gib(torch.cuda.max_memory_allocated())} GiB "
                  f"{time.time() - t0:.0f}s", flush=True)
    except torch.OutOfMemoryError as e:
        row["out_of_memory"] = True
        print(f"out of memory: {str(e)[:200]}", flush=True)
    row |= {"peak_allocated_gib": gib(torch.cuda.max_memory_allocated()),
            "peak_reserved_gib": gib(torch.cuda.max_memory_reserved()), "seconds": round(time.time() - t0)}
    with open(RESULTS, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    print(json.dumps(row))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--length", type=int, default=4096)
    ap.add_argument("--answer", type=int, default=128)
    ap.add_argument("--steps", type=int, default=3)
    ap.add_argument("--head-dtype", choices=["fp32", "bf16"], default="fp32")
    ap.add_argument("--full-logits", action="store_true")
    ap.add_argument("--mem-fraction", type=float, default=0.90)
    main(ap.parse_args())
