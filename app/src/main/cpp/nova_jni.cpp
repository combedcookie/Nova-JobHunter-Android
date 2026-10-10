
#include <jni.h>
#include <string>
#include <vector>
#include <stdexcept>
#include <algorithm>
#include "llama.h"

extern "C" JNIEXPORT jstring JNICALL
Java_com_nova_jobhunter_MainActivity_nativeGenerate(JNIEnv* env, jclass,
    jstring pathJ, jstring promptJ) {
    const char* path=env->GetStringUTFChars(pathJ,nullptr);
    const char* prompt=env->GetStringUTFChars(promptJ,nullptr);
    std::string output;
    llama_model* model=nullptr;
    llama_context* ctx=nullptr;
    llama_sampler* sampler=nullptr;
    try {
        llama_backend_init();
        llama_model_params mp=llama_model_default_params();
        mp.n_gpu_layers=0;
        model=llama_model_load_from_file(path,mp);
        if(!model) throw std::runtime_error("Model load failed");
        llama_context_params cp=llama_context_default_params();
        cp.n_ctx=2048;
        cp.n_batch=512;
        ctx=llama_init_from_model(model,cp);
        if(!ctx) throw std::runtime_error("Context allocation failed");
        const llama_vocab* vocab=llama_model_get_vocab(model);
        std::string input=std::string("<|im_start|>system\nYou are NOVA, a private offline assistant. Answer accurately.\n<|im_end|>\n<|im_start|>user\n")+prompt+"<|im_end|>\n<|im_start|>assistant\n";
        int n=llama_tokenize(vocab,input.c_str(),(int)input.size(),nullptr,0,true,true);
        if(n>=0 || -n>1800) throw std::runtime_error("Prompt too long");
        std::vector<llama_token> tokens(-n);
        n=llama_tokenize(vocab,input.c_str(),(int)input.size(),tokens.data(),(int)tokens.size(),true,true);
        if(n<=0) throw std::runtime_error("Tokenization failed");
        sampler=llama_sampler_init_greedy();
        if(!sampler) throw std::runtime_error("Sampler failed");
        for(int start=0;start<n;start+=512) {
            int count=std::min(512,n-start);
            llama_batch batch=llama_batch_get_one(tokens.data()+start,count);
            if(llama_decode(ctx,batch)!=0) throw std::runtime_error("Prompt decode failed");
        }
        for(int i=0;i<160;i++) {
            llama_token tok=llama_sampler_sample(sampler,ctx,-1);
            if(llama_vocab_is_eog(vocab,tok)) break;
            char piece[4096];
            int len=llama_token_to_piece(vocab,tok,piece,sizeof(piece),0,false);
            if(len<0) throw std::runtime_error("Token conversion failed");
            output.append(piece,len);
            llama_batch batch=llama_batch_get_one(&tok,1);
            if(llama_decode(ctx,batch)!=0) throw std::runtime_error("Generation failed");
        }
    } catch(const std::exception& e) {
        output=std::string("NOVA_ENGINE_ERROR: ")+e.what();
    }
    if(sampler) llama_sampler_free(sampler);
    if(ctx) llama_free(ctx);
    if(model) llama_model_free(model);
    env->ReleaseStringUTFChars(pathJ,path);
    env->ReleaseStringUTFChars(promptJ,prompt);
    return env->NewStringUTF(output.c_str());
}
