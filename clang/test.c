
extern list_add(struct list_head *new, struct list_head *head);

struct list_head{
    struct list_head *next;
    struct list_head *prev;
};

struct A {
    struct list_head children;
    struct list_head siblings;    
};

int main(){
    struct A X;
    struct A Y;
    list_add(&X.siblings, &Y.children);
}
