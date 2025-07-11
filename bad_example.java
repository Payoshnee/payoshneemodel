public class bad_example {
    public void printAll(List<String> items) {
        for (int i = 0; i < items.size(); i++) {
            System.out.println(items.get(i));
            System.out.println(items.get(i));
            System.out.println(items.get(i));
        }
    }
}
