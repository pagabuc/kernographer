//------------------------------------------------------------------------------
// plugin_print_funcnames Clang sample. Demonstrates:
//
// * How to create a Clang plugin.
// * How to use AST actions to access the AST of the parsed code.
//
// Once the .so is built, it can be loaded by Clang. For example:
//
// $ clang -cc1 -load build/plugin_print_funcnames.so -plugin print-fns <cfile>
//
// Taken from the Clang distribution. LLVM's license applies.
//------------------------------------------------------------------------------
// [+] HandleListAdd: list_add_tail_rcu Declared at: net/core/fib_rules.c:119:2
// CallExpr 0x726f950 'void'
// |-ImplicitCastExpr 0x726f938 'void (*)(struct list_head *, struct list_head *)' <FunctionToPointerDecay>
// | `-DeclRefExpr 0x726f7e0 'void (struct list_head *, struct list_head *)' Function 0x60be0e8 'list_add_tail_rcu' 'void (struct list_head *, struct list_head *)'
// |-UnaryOperator 0x726f880 'struct list_head *' prefix '&'
// | `-MemberExpr 0x726f848 'struct list_head':'struct list_head' lvalue ->list 0x6fa9c70
// |   `-ImplicitCastExpr 0x726f830 'struct fib_rules_ops *' <LValueToRValue>
// |     `-DeclRefExpr 0x726f808 'struct fib_rules_ops *' lvalue ParmVar 0x726d660 'ops' 'struct fib_rules_ops *' -> getDecl() -> VarDecl 0x726d9a0 <net/core/fib_rules.c:102:2, col:14> col:14 used net 'struct net *'
// `-UnaryOperator 0x726f918 'struct list_head *' prefix '&'
//   `-MemberExpr 0x726f8e0 'struct list_head':'struct list_head' lvalue ->rules_ops 0x6862008
//     `-ImplicitCastExpr 0x726f8c8 'struct net *' <LValueToRValue>
//       `-DeclRefExpr 0x726f8a0 'struct net *' lvalue Var 0x726d9a0 'net' 'struct net *'

#include "clang/AST/ASTConsumer.h"
#include "clang/AST/RecursiveASTVisitor.h"
#include "clang/Frontend/CompilerInstance.h"
#include "clang/Frontend/FrontendAction.h"
#include "clang/Tooling/Tooling.h"
#include "clang/Frontend/FrontendPluginRegistry.h"
#include "llvm/Support/raw_ostream.h"
#include <sstream>
#include <iterator>
#include <string>
#include <vector>
#include <iostream>
#include "utils.hpp"
#include <jsoncpp/json/json.h>

using namespace clang;

class FindNamedClassVisitor
    : public RecursiveASTVisitor<FindNamedClassVisitor> {
public:
    explicit FindNamedClassVisitor(ASTContext *Context)
        : Context(Context) {}

     bool ElementInList(std::vector<std::string> tv, std::string t){
         return find(tv.begin(), tv.end(), t) != tv.end(); 
     }
    
    std::vector<std::string> TwoParamFunctions {"list_add", "list_add_tail", "list_move_tail",
                                                "list_add_rcu", "list_add_tail_rcu", "hlist_add_head",
                                                "hlist_add_before", "hlist_add_behind", "hlist_add_head_rcu",
                                                "hlist_add_tail_rcu", "hlist_add_before_rcu"};
    
    std::vector<std::string> OneParamFunctions {"list_del", "list_del_rcu"};
    // "list_del_init", "list_del_init_rcu"};

    QualType getQualType(const Type *T){
        QualType QT;
        if (T->isRecordType()){
            const RecordType *RT = T->getAsStructureType();
            QT = RT->desugar();
        }
        else{
            QT = T->getPointeeType();
        }
        return QT;
    }
    
    std::string getTypeStr(const Type *T){
        QualType QT = getQualType(T);
        if(QT.isNull() || T->isVoidType() || T->isVoidPointerType()){
            return "";
        }
        QT = QT.getDesugaredType(*Context);
        return QT.getUnqualifiedType().getAsString();
    }

    std::string getTypeFromExpr(Expr *E){
        const Type *T = E->getType().getTypePtr();
        return getTypeStr(T);
    }
        
    void GetInfoFromArg(Stmt *S, std::vector<std::string> *result, bool *global){
        // DEBUG("[+] Root: \n"); S->dump();
        
        if(dyn_cast<CallExpr>(S) or dyn_cast<CompoundStmt>(S) or dyn_cast<InitListExpr>(S)){
            return;
        }

        if(ArraySubscriptExpr *ASE = dyn_cast<ArraySubscriptExpr>(S)){
            GetInfoFromArg(ASE->getBase(), result, global);            
            return;
        }

        // MemberExpr - [C99 6.5.2.3] Structure and Union Members.  X->F and X.F.
        if( MemberExpr *ME = dyn_cast<MemberExpr>(S)){                
            FieldDecl *FD = dyn_cast<FieldDecl>(ME->getMemberDecl());
            
            // If this field is inside an union            
            if (FD && FD->getParent()->isUnion()){ 
                DEBUG("[-] Field inside a union, aborting and clearing.\n");
                result->clear();                
                return;
            }
            
            std::string FieldName = ME->getMemberDecl()->getNameAsString();
            if(FieldName.length() != 0){
                DEBUG("[!] FieldName = ", FieldName);
                result->push_back(FieldName);
            }
        }
        
        if(DeclRefExpr *DRE = dyn_cast<DeclRefExpr>(S)){
            if(VarDecl *VD = dyn_cast<VarDecl>(DRE->getDecl())){
                // If it is a global variable then we take its name
                if(VD->hasGlobalStorage()){
                    std::string VarName = VD->getDeclName().getAsString();
                    DEBUG("[!] VarName = ", VarName);
                    result->push_back(VarName);
                    *global = true;
                    return;
                }
            
                std::string StructType = getTypeFromExpr(DRE);
                result->push_back(StructType);
                DEBUG("[!] StructType = ", StructType);
                
                Expr *E = VD->getInit();
                if(E)
                    GetInfoFromArg(E, result, global);
            }
        }
        
        // Recursive step        
        for(auto &c: S->children()){
            if(!c)
                return;
            GetInfoFromArg(c, result, global);
        }
        
        return;
    }
    
    std::string ImplodeVector(std::vector<std::string> v){
        const std::string delimiter=".";
        std::ostringstream tmp;
        std::copy(v.rbegin(), v.rend(),
                  std::ostream_iterator<std::string>(tmp, delimiter.c_str()));
        std::string result = tmp.str();
        result.erase(result.size() - 1);
        return result;
    }

    std::string GetLocationInfo(Expr *E){
        std::stringstream info;
        FullSourceLoc FullLocation = Context->getFullLoc(E->getExprLoc());        
        if (FullLocation.isValid() and FullLocation.getFileEntry())
            info << FullLocation.getFileEntry()->getName().str() << ":"
                 << FullLocation.getSpellingLineNumber() << ":"
                 << FullLocation.getSpellingColumnNumber();
        return info.str();
    }
        
    bool HandleCallExpr(CallExpr *CE, bool TwoArgs) {
        std::vector<std::string> head, entry;
        bool entry_global = false, head_global = false;
        
        DEBUG("[+] HandleCE: ",CE->getDirectCallee()->getName().str(),
              " Declared at: ", GetLocationInfo(CE));
        // CE->dump();
        
        DEBUG(" ------------------ Checking argument 0 ------------------\n");
        GetInfoFromArg(CE->getArg(0), &entry, &entry_global);
        
        if(TwoArgs){
            DEBUG(" ------------------ Checking argument 1 ------------------\n");
            GetInfoFromArg(CE->getArg(1), &head, &head_global);
        }
        else
            head = entry;

        if(entry.empty() or head.empty())
            return true;

        Json::Value Root;
        
        if(entry_global)
            Root["entry_global"] = "True";
        if(head_global)
            Root["head_global"] = "True";
        
        Root["head"] = ImplodeVector(head);
        Root["entry"] = ImplodeVector(entry);
        Root["loc"] = GetLocationInfo(CE);

        LogJson(Root);

        return true;
    }
    
    bool VisitCallExpr(CallExpr *CE) {
        FunctionDecl *FD = CE->getDirectCallee();

        if(!FD)
            return true;
        
        if(ElementInList(TwoParamFunctions, FD->getName()))
            HandleCallExpr(CE, true);

        if(ElementInList(OneParamFunctions, FD->getName()))
            HandleCallExpr(CE, false);

        return true;
    }

private:
    ASTContext *Context;
};

class FindNamedClassConsumer : public ASTConsumer {
public:
    explicit FindNamedClassConsumer(ASTContext *Context)
        : Visitor(Context) {}

    virtual void HandleTranslationUnit(ASTContext &Context) {
        Visitor.TraverseDecl(Context.getTranslationUnitDecl());
    }
private:
    FindNamedClassVisitor Visitor;
};

class FindNamedClassAction : public PluginASTAction {
protected:
    std::unique_ptr<clang::ASTConsumer> CreateASTConsumer(
        CompilerInstance &Compiler, llvm::StringRef InFile) override {
        return std::unique_ptr<ASTConsumer>(
        new FindNamedClassConsumer(&Compiler.getASTContext()));
    }
    
    bool ParseArgs(const CompilerInstance &CI,
                   const std::vector<std::string> &args) override {
        return true;
    }
};

static FrontendPluginRegistry::Add<FindNamedClassAction>
X("print-struct", "print function names");
