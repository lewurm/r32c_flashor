#!/usr/bin/env python
import sys, time
from SerialPort_linux import SerialPort, SerialPortException

# baudrate used for initialization
INIT_BAUDRATE = 9600
# baudrate used for communication with the internal bootloader after init
BOOTLOADER_BAUDRATE = 9600
# constant for output
SPLIT = 30

# contains the last received checksum from a READ, WRITE or CHECKSUM command
lastchecksum = 0

class FlashSequence(object):
	def __init__(self, address, data):
		self.address = address
		self.data = data

class MCUStatus(object):
	NOKEY=0
	WRONGKEY=1
	CORRECTKEY=2
	key = 0

	def setKeyStatus(self, key):
		self.key = key

	def getKeyStatus(self):
		return self.key


def dec2hex(n):
	"""return the hexadecimal string representation of integer n"""
	return "%X" % n

def sendbyte(byte):
	"""
	send a byte to the TTY-device
	"""
	tty.write(chr(byte))

def sendword(word):
	"""
	send a word to the TTY-device
	"""
	sendbyte(word & 0xFF)
	sendbyte((word >> 8) & 0xFF)

def senddword(dword):
	"""
	send a dword to the TTY-device
	"""
	sendbyte(dword & 0xFF)
	sendbyte((dword >> 8) & 0xFF)
	sendbyte((dword >> 16) & 0xFF)
	sendbyte((dword >> 24) & 0xFF)

def recvbyte():
	"""
	receive a byte from the TTY-device
	"""
	return ord(tty.read())

def recvchecksum():
	"""
	receive checksum from the bootROM firmware
	"""
	global lastchecksum
	lastchecksum = recvbyte()
	lastchecksum |= (recvbyte() << 8)

def bootromread(address, size):
	"""
	send a READ-command to the bootROM-firmware
	"""
	# send READ command
	sendbyte(0x01)
	if (recvbyte() != 0xF1):
		raise Exception
	sendbyte(0x02)
	if (recvbyte() != 0x82):
		raise Exception
	# tell desired address and size
	senddword(address)
	sendword(size)
	# get binary stream of data
	data = []
	for _ in range(0, size):
		data.append(recvbyte())
	# get checksum
	recvchecksum()
	return data

def bootromwrite(address, size, data):
	"""
	send a WRITE-command to the bootROM-firmware
	"""
	# send WRITE command
	sendbyte(0x01)
	if (recvbyte() != 0xF1):
		raise Exception
	sendbyte(0x03)
	if (recvbyte() != 0x83):
		raise Exception
	# tell desired address and size
	senddword(address)
	sendword(size)
	# write binary stream of data
	for i in range(0, size):
		sendbyte(data[i])
	# get checksum
	recvchecksum()

def bootromcall(address):
	"""
	send a CALL-command to the bootROM-firmware
	"""
	# send CALL command
	sendbyte(0x01)
	if (recvbyte() != 0xF1):
		raise Exception
	sendbyte(0x04)
	if (recvbyte() != 0x84):
		raise Exception
	# tell desired address
	senddword(address)
	# wait for return parameter - not needed here!
	#return recvbyte()

# TODO: test this function!
def bootromchecksum():
	"""
	send a CHECKSUM-command to the bootROM-firmware
	"""
	# call CHECKSUM command
	sendbyte(0x01)
	if (recvbyte() != 0xF1):
		raise Exception
	sendbyte(0x05)
	if (recvbyte() != 0x84):
		raise Exception
	# get checksum
	recvchecksum()

def bootrombaudrate(baudrate):
	"""
	send a BAUDRAME-command to the bootROM-firmware
	"""
	# send BAUDRATE command
	sendbyte(0x01)
	if (recvbyte() != 0xF1):
		raise Exception
	sendbyte(0x06)
	if (recvbyte() != 0x86):
		raise Exception
	# send desired baudrate
	senddword(baudrate)

def pkernchiperase():
	"""
	send a CHIPERASE-command to the pkernel-firmware
	"""
	sendbyte(0x15)
	if (recvbyte() != 0x45):
		raise Exception
	# wait till completion...
	if (recvbyte() != 0x23):
		raise Exception

def pkernerase(address, size):
	"""
	send a ERASE-command to the pkernel-firmware
	"""
	sendbyte(0x12)
	if (recvbyte() != 0x11):
		raise Exception
	senddword(address)
	sendword(size)
	if (recvbyte() != 0x18):
		raise Exception

def pkernwrite(address, size, data):
	"""
	send a WRITE-command to the pkernel-firmware
	"""
	# send WRITE command
	sendbyte(0x13)
	if (recvbyte() != 0x37):
		raise Exception
	# tell desired address and size
	senddword(address)
	sendword(size)

	# write binary stream of data
	for i in range(0, size):
		sendbyte(data[i])

	if (recvbyte() != 0x28):
		raise Exception

def readmhxfile(filename): # desired mhx filename
	"""
	proceeds a MHX-File
	"""
	filep = open(filename, "r")
	retval = [] # returns a list of FlashSequence objects
	linecount = 0
	for line in filep:
		linecount += 1
		# get rid of newline characters
		line = line.strip()

		# we're only interested in S2 (data sequence with 3 address bytes)
		# records by now
		if line[0:2] == "S2":
			byte_count = int(line[2:4], 16)
			# just to get sure, check if byte count field is valid
			if (len(line)-4) != (byte_count*2):
				print sys.argv[0] + ": Warning - inavlid byte count field in " + \
					sys.argv[1] + ":" + str(linecount) + ", skipping line!"
				continue

			# address and checksum bytes are not needed
			byte_count -= 4
			address = int(line[4:10], 16)
			datastr = line[10:10+byte_count*2]

			# convert data hex-byte-string to real byte data list
			data = []
			for i in range(0, len(datastr)/2):
				data.append(int(datastr[2*i:2*i+2], 16))

			# add flash sequence to our list
			retval.append(FlashSequence(address, data))
	filep.close()
	return retval

def clearStatus():
	sendbyte(0x50);

def getStatus():
	sendbyte(0x70) # get status
	status1 = recvbyte()
	status2 = recvbyte()
	print "status1: " + dec2hex(status1)
	print "status2: " + dec2hex(status2)
	print "bootloader ready: " + str(testBit(status1, 7))
	key1 = testBit(status2, 2)
	key2 = testBit(status2, 3)

	status = MCUStatus()

	if key1 == 1 and key2 == 1:
		status.setKeyStatus(MCUStatus.CORRECTKEY)
		print "correct key"
	elif key1 == 1 and key2 == 0:
		status.setKeyStatus(MCUStatus.WRONGKEY)
		print "wrong key"
	elif key1 == 0 and key2 == 0:
		status.setKeyStatus(MCUStatus.NOKEY)
		print "no key"
	else:
		print "w00t"
		raise Exception('wrongkeybits!')

	return status
	

def testBit(byte, pos):
	bitmask = 1 << pos
	return (byte & bitmask) >> pos

def sendKeyAddr(addr):
	sendbyte(0x48)
	sendbyte((addr >> 24) & 0xFF)
	sendbyte(0xF5)
	sendbyte(addr& 0xFF)
	sendbyte((addr >> 8) & 0xFF)
	sendbyte((addr >> 16) & 0xFF)

def sendPageAddr(addr, cmd):
	sendbyte(0x48)
	sendbyte((addr >> 24) & 0xFF)
	sendbyte(cmd)
	sendbyte((addr >> 8) & 0xFF)
	sendbyte((addr >> 16) & 0xFF)


def sendKey(addr, key):
	print "Sending key: " + dec2hex(key) + " for addr: " + dec2hex(addr)
	sendKeyAddr(addr)
	sendbyte(0x07)
	for i in range(7):
		sendbyte((key >> i) & 0xFF)

def readPage(addr):
	sendPageAddr(addr, 0xff)
	for i in range(0, 255):
		print "byte" + str(i) + ": " + dec2hex(recvbyte())


def usage(execf):
	"""
	print usage of frprog
	"""
	print "Usage: " + execf + " <target mhx-file> [-d DEVICE]"

def main(argv=None):
	"""
	main function of frprog
	"""
	# check command line arguments
	if argv is None:
		argv = sys.argv

	if len(argv) == 2 and (argv[1] == "-v" or argv[1] == "--version"):
		print "Version: %VERSION%"
		return 0

	#TODO: ...
	#if len(argv) != 2 and len(argv) != 4:
	if len(argv) != 1:
		usage(argv[0])
		return 1

	# standard serial device to communicate with
	device = "/dev/ttyUSB0"

	# overrule standard device if provided with -d
	if len(argv) == 4:
		if argv[2] == "-d":
			device = argv[3]
		else:
			usage(argv[0])
			return 1

	# read in data from mhx-files before starting
	#try:
		#try:
			#bootloaderseqs = readmhxfile("pkernel/pkernel.mhx")
		#except IOError as _:
			#bootloaderseqs = readmhxfile("%PREFIX%/share/frprog/pkernel.mhx")
		#pkernelseqs = readmhxfile(argv[1])
	#except IOError as error:
		#print argv[0] + ": Error - couldn't open file " + error.filename + "!"
		#return 1

	print "Initializing serial port..."
	global tty
	try:
		tty = SerialPort(device, 100, INIT_BAUDRATE)
	except SerialPortException as error:
		print error + " Device: " + device + "!"
		return 1


	raw_input("Please push the RESET button on your board and press any ENTER to continue...")
	#TODO: wait for user input

	time.sleep(0.003)


	for i in range(16):
		sendbyte(0x00)
		time.sleep(0.021) #wait 21ms
	
	sendbyte(0xb0) # set 9600 baud
	print "status byte after baudset: ", recvbyte()

	sendbyte(0xfb) # get version

	version = ""
	for i in range(8):
		version = version + chr(recvbyte())

	print "chipversion: ", version

	clearStatus()

	correct = 0
	if getStatus().getKeyStatus() == MCUStatus.CORRECTKEY:
		correct = 1
	else:
		for i in range(0xFFFFFFE8, 0xFFFFFFEE):

			sendKey(i, 0x00000000000000)
			status = getStatus()
			if status.getKeyStatus() == MCUStatus.CORRECTKEY:
				correct = 1
				break
			clearStatus()


			sendKey(i, 0xFFFFFFFFFFFFFF)
			status = getStatus()
			if status.getKeyStatus() == MCUStatus.CORRECTKEY:
				correct = 1
				break
			clearStatus()

	if correct == 0:
		print "No Valid Key found! Powercycle the board or provide correct key!"
		return 1

	readPage(0xffff0000)


	# save time at this point for evaluating the duration at the end
	starttime = time.time()


if __name__ == '__main__':
	sys.exit(main())
