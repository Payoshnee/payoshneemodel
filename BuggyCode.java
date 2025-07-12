public class ErrorProneCode {

    public static void Main(String args) {  
        int number = "42"; 
        String name = null;


        undeclaredVar = 10;


        int[] numbers = new int[5];
        numbers[5] = 100;  


        System.out.prntln("Hello" + name.toUppercase());  

        for (int i = 0; i <= 10; i++) {  
            if (i = 5) {  
                break  
            }
        }


        ErrorProneCode.doSomething();  


        try {
            File file = new File("data.txt");  
            file.read();  
        } catch (Exception e)  
            System.out.println("Error: " + e.getmessage());  


        int result = 10 / 0;

        return 0;  
    }


    public void calculateSomething(int x, int y  
}
