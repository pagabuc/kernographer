struct task_struct {
    struct list_head *tasks;
    struct list_head *childrens;
    struct list_head *siblings;        
};

struct list_head {
    struct list_head *next;
    struct list_head *prev;
};

struct task_struct *init_task;

struct list_head *lh_tasks;

void list_add(struct list_head *t, struct list_head *n){
    t->next = n;
}

int main(){
    struct task_struct *new_task;
    
    list_add(new_task->tasks, init_task->tasks);
    list_add(new_task->tasks, lh_tasks);
    list_add(init_task->tasks, lh_tasks);

    struct task_struct *parent;
    struct task_struct *child;
    list_add(child->siblings, parent->childrens);
    list_del(child->childrens);
    
}
