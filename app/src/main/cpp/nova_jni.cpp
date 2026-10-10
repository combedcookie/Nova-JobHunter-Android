// NOVA_PERSISTENT_V1: process-scoped model/context, serialized inference
#include <jni.h>
#include <string>
#include <vector>
#include <stdexcept>
#include <algorithm>
#include <mutex>
#include <atomic>
#include <chrono>
#include <memory>
#include "llama.h"

namespace {
std::mutex engine_mutex;
std::atomic<bool> cancel_requested{false};
llama_model *cached_model = nullptr;
llama_context *cached_context = nullptr;
std::string cached_path;

void unload() {
    if (cached_context) { llama_free(cached_context); cached_context = nullptr; }
    if (cached_model) { llama_model_free(cached_model); cached_model = nullptr; }
    cached_path.clear();
}
void ensure_loaded(const std::string &path) {
    if (cached_model && cached_context && cached_path == path) return;
    unload();
    static std::once_flag init_flag;
    std::call_once(init_flag, [] { llama_backend_init(); });
    llama_model_params mp = llama_model_default_params();
    mp.n_gpu_layers = 0;
    cached_model = llama_model_load_from_file(path.c_str(), mp);
    if (!cached_model) throw std::runtime_error("Model load failed");
    llama_context_params cp = llama_context_default_params();
    cp.n_ctx = 2048;
    cp.n_batch = 512;
    cached_context = llama_init_from_model(cached_model, cp);
    if (!cached_context) { unload(); throw std::runtime_error("Context allocation failed"); }
    cached_path = path;
}
struct SamplerGuard {
    llama_sampler *value;
    explicit SamplerGuard(llama_sampler *s) : value(s) {}
    ~SamplerGuard() { if (value) llama_sampler_free(value); }
};
struct UtfGuard {
    JNIEnv *env;
    jstring original;
    const char *value;
    UtfGuard(JNIEnv *e, jstring j) : env(e), original(j), value(e->GetStringUTFChars(j, nullptr)) {}
    ~UtfGuard() { if (value) env->ReleaseStringUTFChars(original, value); }
};
}
extern "C" JNIEXPORT jstring JNICALL
Java_com_nova_jobhunter_MainActivity_nativeGenerate(JNIEnv *env, jclass,
                                                     jstring pathJ, jstring promptJ) {
    if (!pathJ || !promptJ) return env->NewStringUTF("NOVA_ENGINE_ERROR: Missing input");
    UtfGuard path(env, pathJ), prompt(env, promptJ);
    if (!path.value || !prompt.value) return nullptr;
    std::string output;
    try {
        std::lock_guard<std::mutex> lock(engine_mutex);
        cancel_requested.store(false);
        ensure_loaded(path.value);
        // NOVA_NONTHINK_V1: Qwen3 /no_think; preserve native inference semantics.
        // Each request is independent; clear prior KV state but retain model weights.
        llama_memory_clear(llama_get_memory(cached_context), true);
        const llama_vocab *vocab = llama_model_get_vocab(cached_model);
        std::string input = std::string("<|im_start|>system\nYou are NOVA, a private offline assistant. Answer accurately. Respond directly and concisely. For this app, do not output internal reasoning.\n<|im_end|>\n<|im_start|>user\n")
            + prompt.value + "\n/no_think<|im_end|>\n<|im_start|>assistant\n";
        int required = llama_tokenize(vocab, input.c_str(), (int)input.size(), nullptr, 0, true, true);
        if (required >= 0 || -required > 1700) throw std::runtime_error("Prompt too long");
        std::vector<llama_token> tokens((size_t)-required);
        int n = llama_tokenize(vocab, input.c_str(), (int)input.size(), tokens.data(), (int)tokens.size(), true, true);
        if (n <= 0) throw std::runtime_error("Tokenization failed");
        SamplerGuard sampler(llama_sampler_init_greedy());
        if (!sampler.value) throw std::runtime_error("Sampler initialization failed");
        for (int start = 0; start < n; start += 512) {
            int count = std::min(512, n - start);
            llama_batch batch = llama_batch_get_one(tokens.data() + start, count);
            if (llama_decode(cached_context, batch) != 0) throw std::runtime_error("Prompt decode failed");
        }
        // Reserve room for generation in the 2048-token context.
        const int max_new = std::min(256, 2048 - n - 1);
        const auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(120);
        for (int i = 0; i < max_new; ++i) {
            if(cancel_requested.load())throw std::runtime_error("Generation cancelled");
            if(std::chrono::steady_clock::now()>deadline)throw std::runtime_error("Generation time limit reached");
            llama_token tok = llama_sampler_sample(sampler.value, cached_context, -1);
            if (llama_vocab_is_eog(vocab, tok)) break;
            char piece[4096];
            int len = llama_token_to_piece(vocab, tok, piece, sizeof(piece), 0, false);
            if (len < 0) throw std::runtime_error("Token conversion failed");
            output.append(piece, (size_t)len);
            llama_batch batch = llama_batch_get_one(&tok, 1);
            if (llama_decode(cached_context, batch) != 0) throw std::runtime_error("Generation failed");
        }
    } catch (const std::exception &e) {
        output = std::string("NOVA_ENGINE_ERROR: ") + e.what();
    }
    // NewStringUTF requires modified UTF-8; construct Java UTF-8 string through byte[] instead.
    jbyteArray bytes=env->NewByteArray((jsize)output.size());
    if(!bytes)return nullptr;
    env->SetByteArrayRegion(bytes,0,(jsize)output.size(),reinterpret_cast<const jbyte*>(output.data()));
    jclass stringClass=env->FindClass("java/lang/String");
    if(!stringClass)return nullptr;
    jmethodID ctor=env->GetMethodID(stringClass,"<init>","([BLjava/lang/String;)V");
    if(!ctor)return nullptr;
    jstring charset=env->NewStringUTF("UTF-8");
    return (jstring)env->NewObject(stringClass,ctor,bytes,charset);
}

extern "C" JNIEXPORT void JNICALL
Java_com_nova_jobhunter_MainActivity_nativeCancelGeneration(JNIEnv *, jclass) {
    cancel_requested.store(true);
}
