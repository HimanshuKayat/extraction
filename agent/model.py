from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import torch

from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
)


class ModelClient(Protocol):

    def generate(
        self,
        messages: list[dict[str, str]],
        mode: str = "tool_selection",
    ) -> str:
        ...


@dataclass
class GenerationConfig:

    enable_thinking: bool = False

    # Keep generation deliberately small on a Tesla T4.
    max_new_tokens: int = 128

    temperature: float = 0.0

    do_sample: bool = False


class QwenModel:

    DEFAULT_MODEL = "Qwen/Qwen3-8B"

    # T4-safe defaults.
    MAX_INPUT_TOKENS = 4096

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        load_in_4bit: bool = True,
        device_map: str | dict = "auto",
    ) -> None:

        self.model_name = model_name

        print(
            f"Loading model: {model_name}"
        )

        self._tokenizer = (
            AutoTokenizer.from_pretrained(
                model_name,
                trust_remote_code=True,
            )
        )

        quantization_config = None

        if load_in_4bit:

            quantization_config = (
                BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_quant_type="nf4",
                    bnb_4bit_compute_dtype=(
                        torch.float16
                    ),
                    bnb_4bit_use_double_quant=True,
                )
            )

        self._model = (
            AutoModelForCausalLM.from_pretrained(
                model_name,
                quantization_config=(
                    quantization_config
                ),
                device_map=device_map,
                dtype=torch.float16,
                trust_remote_code=True,
                low_cpu_mem_usage=True,
            )
        )

        self._model.eval()

        # ------------------------------------------------------
        # Generation profiles
        # ------------------------------------------------------

        self.generation_configs = {

            "tool_selection": GenerationConfig(
                enable_thinking=False,
                max_new_tokens=128,
                temperature=0.0,
                do_sample=False,
            ),

            "reasoning": GenerationConfig(
                enable_thinking=True,
                max_new_tokens=256,
                temperature=0.6,
                do_sample=True,
            ),
        }

        print(
            "Qwen model loaded."
        )

        self._print_memory()

    # ==========================================================
    # MEMORY
    # ==========================================================

    def _print_memory(
        self,
    ) -> None:

        if not torch.cuda.is_available():
            return

        allocated = (
            torch.cuda.memory_allocated()
            / 1024**3
        )

        reserved = (
            torch.cuda.memory_reserved()
            / 1024**3
        )

        total = (
            torch.cuda.get_device_properties(
                0
            ).total_memory
            / 1024**3
        )

        print(
            "GPU memory:"
        )

        print(
            f"  Total:     {total:.2f} GB"
        )

        print(
            f"  Allocated: {allocated:.2f} GB"
        )

        print(
            f"  Reserved:  {reserved:.2f} GB"
        )

    # ==========================================================
    # INPUT PREPARATION
    # ==========================================================

    def _prepare_inputs(
        self,
        messages: list[dict[str, str]],
        config: GenerationConfig,
    ) -> dict[str, torch.Tensor]:
        """
        Convert the conversation into model inputs.

        The token limit is intentionally bounded because the T4
        has limited VRAM and attention memory grows with context.
        """

        prompt = (
            self._tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=(
                    config.enable_thinking
                ),
            )
        )

        inputs = self._tokenizer(
            prompt,
            return_tensors="pt",
            truncation=True,
            max_length=self.MAX_INPUT_TOKENS,
        )

        # Qwen is quantized but its active computation is on the
        # model's execution device.
        device = self._model.device

        inputs = {
            key: value.to(device)
            for key, value in inputs.items()
        }

        return inputs

    # ==========================================================
    # GENERATION
    # ==========================================================

    def generate(
        self,
        messages: list[dict[str, str]],
        mode: str = "tool_selection",
    ) -> str:

        if mode not in self.generation_configs:

            raise ValueError(
                f"Unknown generation mode: {mode}"
            )

        config = (
            self.generation_configs[
                mode
            ]
        )

        inputs = self._prepare_inputs(
            messages,
            config,
        )

        generation_kwargs = {
            "max_new_tokens": (
                config.max_new_tokens
            ),
            "do_sample": (
                config.do_sample
            ),
            "pad_token_id": (
                self._tokenizer.eos_token_id
            ),
            "use_cache": True,
        }

        if config.do_sample:

            generation_kwargs[
                "temperature"
            ] = config.temperature

        # ------------------------------------------------------
        # Log context size before generation.
        # ------------------------------------------------------

        input_tokens = (
            inputs["input_ids"]
            .shape[-1]
        )

        print(
            f"[QWEN] mode={mode} "
            f"input_tokens={input_tokens} "
            f"max_new_tokens="
            f"{config.max_new_tokens}"
        )

        self._print_memory()

        try:

            with torch.inference_mode():

                outputs = (
                    self._model.generate(
                        **inputs,
                        **generation_kwargs,
                    )
                )

        except torch.cuda.OutOfMemoryError:

            print(
                "[QWEN] CUDA OOM during generation."
            )

            # Release temporary tensors.
            del inputs

            if torch.cuda.is_available():

                torch.cuda.empty_cache()

            raise

        input_length = (
            inputs["input_ids"]
            .shape[-1]
        )

        generated = outputs[
            0,
            input_length:,
        ]

        result = (
            self._tokenizer.decode(
                generated,
                skip_special_tokens=True,
            )
            .strip()
        )

        del outputs
        del inputs

        if torch.cuda.is_available():

            torch.cuda.empty_cache()

        return result
