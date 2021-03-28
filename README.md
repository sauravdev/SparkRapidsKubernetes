# SparkRapidsKubernetes

## Step 1 - Install NVIDIA Drivers

sudo apt-get update
sudo add-apt-repository ppa:graphics-drivers/ppa
sudo apt install nvidia-driver-440
sudo apt install nvidia-cuda-toolkit
sudo reboot
nvidia-smi

## Step 2 - Install Docker

https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html#installing-on-ubuntu-and-debian

## Step 3 - Install K8s Components 

https://docs.nvidia.com/datacenter/cloud-native/kubernetes/k8s-containerd.html#ubuntu-k8s

Repeat Above steps for each node of the cluster

## Step 4 - K8s Deployment

Start by disabling the swap memory on each server:

`sudo swapoff -a`

Assign Unique Hostname for Each Server Node .Decide which server to set as the master node. Then enter the command:

`sudo hostnamectl set-hostname master-node`

Next, set a worker node hostname by entering the following on the worker server:

`sudo hostnamectl set-hostname worker01`

If you have additional worker nodes, use this process to set a unique hostname on each.

Initialize Kubernetes on Master Node

Switch to the master server node, and enter the following:

`sudo kubeadm init --pod-network-cidr=<IP>/16`

Once this command finishes, it will display a kubeadm join message at the end. Make a note of the whole entry. This will be used to join the worker nodes to the cluster.

To start using your cluster, you need to run the following as a regular user:
 
```
mkdir -p $HOME/.kube
sudo cp -i /etc/kubernetes/admin.conf $HOME/.kube/config
sudo chown $(id -u):$(id -g) $HOME/.kube/config
```
Label the node

`kubectl label node worker01=worker`

## Step 5 - Deploy Pod Network to Cluster
A Pod Network is a way to allow communication between different nodes in the cluster. This tutorial uses the flannel virtual network.
Enter the following:

`wget https://raw.githubusercontent.com/coreos/flannel/master/Documentation/kube-flannel.yml`

Change network ip in net-conf.json

`sudo kubectl apply -f kube-flannel.yml`

Allow the process to complete.

Verify that everything is running and communicating:

`kubectl get pods --all-namespaces`

## Step 6 - Join Worker Node(s) to Cluster

As indicated in Step 4, you can enter the kubeadm join command on each worker node to connect it to the cluster.
Switch to the worker01 system and enter the command you noted from Step 4.

Repeat for each worker node on the cluster. Wait a few minutes; then you can check the status of the nodes.
Switch to the master server, and enter:
kubectl get nodes
The system should display the worker nodes that you joined to the cluster.

## Step 7 - SPARK RAPIDS Deployment 

Download relevant Files, Jars etc

https://nvidia.github.io/spark-rapids/docs/get-started/getting-started-on-prem.html

Kubernetes requires a Docker image to run Spark. Generally everything needed is in the Docker image - Spark, the RAPIDS Accelerator for Spark jars, and the discovery script. See this Dockerfile.cuda example.
This assumes you have Kubernetes already installed and setup. These instructions do not cover how to setup a Kubernetes cluster.
Install Spark, the RAPIDS Accelerator for Spark jars, and the GPU discovery script on the node from which you are going to build your Docker image. Note that you can download these into a local directory and untar the Spark .tar.gz rather than installing into a location on the machine. Also include the mortgage_etl.py

```
wget https://mirrors.estointernet.in/apache/spark/spark-3.1.1/spark-3.1.1-bin-hadoop3.2.tgz
wget https://repo1.maven.org/maven2/com/nvidia/rapids-4-spark_2.12/0.3.0/rapids-4-spark_2.12-0.3.0.jar
 
wget https://repo1.maven.org/maven2/ai/rapids/cudf/0.17/cudf-0.17-cuda10-1.jar
tar -xvzf spark-3.1.1-bin-hadoop3.2.tgz

wget https://raw.githubusercontent.com/apache/spark/master/examples/src/main/scripts/getGpusResources.sh
 
wget http://rapidsai-data.s3-website.us-east-2.amazonaws.com/notebook-mortgage-data/mortgage_2000.tgz 
mkdir -p /spark-3.1.1-bin-hadoop3.2/usecase/tables/mortgage
mkdir -p /spark-3.1.1-bin-hadoop3.2/usecase/tables/mortgage_parquet_gpu/perf
mkdir -p /spark-3.1.1-bin-hadoop3.2/usecase/tables/mortgage_parquet_gpu/acq
mkdir -p /spark-3.1.1-bin-hadoop3.2/usecase/mortgage_parquet_gpu/output
tar xfvz /mortgage_2000.tgz --directory /spark-3.1.1-bin-hadoop3.2/usecase/tables/mortgage
cp rapids-4-spark_2.12-0.4.1.jar spark-3.1.1-bin-hadoop3.2/jars/
```

Create your Docker image.

`sudo docker build . -f Dockerfile.cuda -t ubuntu18cuda10-1-sparkrapidsplugin`
 
Create or modify /etc/docker/daemon.json on the client machine so as to create a local registry server (optional)
 
```
{
    "runtimes": {
        "nvidia": {
            "path": "nvidia-container-runtime",
            "runtimeArgs": []
        }
  }, "insecure-registries":["<IP>:5000"]
}
``` 
 
 
Restart docker daemon
 
```
sudo /etc/init.d/docker restart
```

Start the local registry server

`sudo docker run -d -p 5000:5000 --restart=always --name registry registry:2`
 
Tag and Push Docker to Registry

```
 
sudo docker tag ubuntu18cuda10-1-sparkrapidsplugin:latest 10.117.17.33:5000/spark-master
 
sudo docker push 10.117.17.33:5000/spark-master
 
docker image ls ubuntu18cuda10-1-sparkrapidsplugin
``` 
`ufw disable (optional)`

Create Servce Account and give RBAC Controls

```
kubectl create serviceaccount spark
 
kubectl create clusterrolebinding spark-role --clusterrole=edit --serviceaccount=default:spark --namespace=default
```

Launch Spark job

```
bin/pyspark \
--master k8s://https://<IP>:6443 \
--deploy-mode cluster \
--conf spark.rapids.sql.concurrentGpuTasks=1 \
--driver-memory 2G \
--conf spark.executor.memory=4G \
--conf spark.executor.cores=4 \
--conf spark.task.cpus=1 \
--conf spark.task.resource.gpu.amount=0.25 \
--conf spark.rapids.memory.pinnedPool.size=2G \
--conf spark.locality.wait=0s \
--conf spark.sql.files.maxPartitionBytes=512m \
--conf spark.sql.shuffle.partitions=10 \
--conf spark.plugins=com.nvidia.spark.SQLPlugin \
--conf spark.executor.resource.gpu.discoveryScript=/opt/sparkRapidsPlugin/getGpusResources.sh \
--conf spark.executor.resource.gpu.vendor=nvidia.com \
--conf spark.executor.instances=2 \
--conf spark.kubernetes.container.image=<IP>:5000/spark-master:latest \
--conf spark.kubernetes.authenticate.driver.serviceAccountName=spark \
local:///opt/spark/examples/mortgage_etl.py
```

See the pod status

`kubectl get pods`
 
See pod logs
`kubectl -n=default logs -f <pod name>`

