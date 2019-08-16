#include <jsoncpp/json/json.h>

Json::Value MapToJson(std::map<std::string, std::string> m){
    Json::Value V;
    for (auto&& element: m) {
        V[element.first] = element.second;
    }
    return V;
}

void LogJson(Json::Value Root){
    Json::FastWriter fast;        
    std::string sFast = "\n" + fast.write(Root);
    llvm::errs() << sFast;
}

std::stringstream log_stream; 

template <typename T>
void DEBUG(T e) {
    log_stream << e << "\n";
    // llvm::errs() << log_stream.str();
    log_stream.str("");
}

template <typename T, typename... Args>
void DEBUG(T e, Args... args) {
    log_stream << e << " ";
    DEBUG(args...);
}
